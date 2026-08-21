import hashlib
import logging
import os
import queue
import threading
import time

from pathlib import Path
from typing import Dict

import aimrocks.errors

from aim.sdk.repo import INDEX_DB_OPEN_TIMEOUT, ContainerConfig, Repo
from filelock import Timeout
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import ObservedWatch
from watchdog.observers.polling import PollingObserver


logger = logging.getLogger(__name__)


class NewChunkCreatedHandler(FileSystemEventHandler):
    def __init__(self, manager):
        self.manager = manager
        self.known_chunks = set(p.name for p in self.manager.chunks_dir.iterdir() if p.is_dir())

    def on_modified(self, event):
        if event.is_directory and Path(event.src_path) == self.manager.chunks_dir:
            current_chunks = set(p.name for p in self.manager.chunks_dir.iterdir() if p.is_dir())
            new_chunks = current_chunks - self.known_chunks
            for chunk_name in new_chunks:
                chunk_path = self.manager.chunks_dir / chunk_name
                logger.debug(f'Detected new chunk directory: {chunk_name}')
                self.manager.monitor_chunk_directory(chunk_path)
            self.known_chunks = current_chunks


class ChunkChangedHandler(FileSystemEventHandler):
    def __init__(self, manager):
        self.manager = manager
        self.pending_events = set()
        self.lock = threading.Lock()

    def _trigger_event(self, run_hash):
        with self.lock:
            if run_hash not in self.pending_events:
                self.pending_events.add(run_hash)
                threading.Timer(0.5, self._process_event, [run_hash]).start()

    def _process_event(self, run_hash):
        with self.lock:
            if run_hash in self.pending_events:
                self.pending_events.remove(run_hash)
                logger.debug(f'Triggering indexing for run {run_hash}')
                self.manager.add_run_to_queue(run_hash)

    def on_any_event(self, event):
        if event.is_directory:
            return

        event_path = Path(event.src_path)
        parent_dir = event_path.parent
        run_hash = parent_dir.name

        # Ensure the parent directory is directly inside meta/chunks/
        if parent_dir.parent != self.manager.chunks_dir:
            logger.debug(f'Skipping event outside valid chunk directory: {event.src_path}')
            return

        if event_path.name.startswith('LOG'):
            logger.debug(f'Skipping event for LOG-prefixed file: {event.src_path}')
            return

        logger.debug(f'Detected change in {event.src_path}')
        self._trigger_event(run_hash)


class RepoIndexManager:
    index_manager_pool = {}

    @classmethod
    def get_index_manager(cls, repo: Repo):
        mng = cls.index_manager_pool.get(repo.path, None)
        if mng is None:
            mng = RepoIndexManager(repo)
            cls.index_manager_pool[repo.path] = mng
        return mng

    def __init__(self, repo: Repo):
        self.repo_path = repo.path
        self.repo = repo
        self.chunks_dir = Path(self.repo_path) / 'meta' / 'chunks'
        self.chunks_dir.mkdir(parents=True, exist_ok=True)

        self._corrupted_runs = set()
        self._failed_attempts: Dict[str, int] = dict()
        self._stale_handle_retry = False

        self.indexing_queue = queue.PriorityQueue()
        self.lock = threading.Lock()

        self.new_chunk_observer = Observer()
        self.chunk_change_observer = PollingObserver()

        self.new_chunk_handler = NewChunkCreatedHandler(self)
        self.chunk_change_handler = ChunkChangedHandler(self)
        self._watches: Dict[str, ObservedWatch] = dict()
        self.new_chunk_observer.schedule(self.new_chunk_handler, self.chunks_dir, recursive=False)

        self._stop_event = threading.Event()
        self._index_thread = None
        self._monitor_thread = None

    def start(self):
        self._stop_event.clear()
        self.new_chunk_observer.start()
        self.chunk_change_observer.start()

        if not self._index_thread or not self._index_thread.is_alive():
            self._index_thread = threading.Thread(target=self._process_indexing_queue, daemon=True)
            self._index_thread.start()

        if not self._monitor_thread or not self._monitor_thread.is_alive():
            self._monitor_thread = threading.Thread(target=self._monitor_existing_chunks, daemon=True)
            self._monitor_thread.start()

    def stop(self):
        self._stop_event.set()
        self.new_chunk_observer.stop()
        self.chunk_change_observer.stop()
        if self._monitor_thread:
            self._monitor_thread.join()
        if self._index_thread:
            self._index_thread.join()

    def _monitor_existing_chunks(self):
        while not self._stop_event.is_set():
            try:
                self._scan_existing_chunks()
            except Exception as e:
                logger.error(f'_monitor_existing_chunks iteration failed: {e}')
            time.sleep(5)

    def _scan_existing_chunks(self):
        """Queue every run whose index entry is out of date.

        This is the only path that picks up a run nobody is watching, so a failure here
        stops new runs from ever being indexed.
        """
        try:
            index_db = self.repo.request_tree('meta', read_only=True)
            monitored_chunks = set(self._watches.keys())
            for chunk_path in self.chunks_dir.iterdir():
                try:
                    if (
                        chunk_path.is_dir()
                        and chunk_path.name not in monitored_chunks
                        and self._is_run_index_outdated(chunk_path.name, index_db)
                    ):
                        logger.debug(f'Monitoring existing chunk: {chunk_path}')
                        self.monitor_chunk_directory(chunk_path)
                        logger.debug(f'Triggering indexing for run {chunk_path.name}')
                        self.add_run_to_queue(chunk_path.name)
                except aimrocks.errors.RocksIOError as e:
                    # The read-only handle still refers to sst files a compaction has
                    # since removed. Every remaining chunk of this scan would fail the
                    # same way, so give up on the stale handle and rescan with a fresh
                    # one rather than skipping the rest of the runs.
                    logger.debug(f'Index db handle went stale, restarting scan: {e}')
                    return self._rescan_with_fresh_handle()
                except Exception as e:
                    logger.warning(f'Error checking chunk {chunk_path}: {e}')
        finally:
            # Drop only the handle this scan opened. Clearing the whole pool from here
            # would race the indexing thread, which relies on it to close the read-write
            # index handle before releasing the cross-process lock.
            self.repo.container_pool.pop(ContainerConfig('meta', None, True), None)

    def _rescan_with_fresh_handle(self):
        if self._stale_handle_retry:
            # Already retried once for this scan; the next 5s tick will try again.
            return
        self._stale_handle_retry = True
        try:
            self.repo.container_pool.pop(ContainerConfig('meta', None, True), None)
            self._scan_existing_chunks()
        finally:
            self._stale_handle_retry = False

    def _stop_monitoring_chunk(self, run_hash):
        watch = self._watches.pop(run_hash, None)
        if watch:
            self.chunk_change_observer.unschedule(watch)
            logger.debug(f'Stopped monitoring chunk: {run_hash}')

    # Number of consecutive failures before a run is given up on. A single transient
    # error (busy index db, exhausted file descriptors) must not exclude a run from
    # indexing for the whole lifetime of the process.
    MAX_INDEX_ATTEMPTS = 5

    def _record_failure(self, run_hash, reason):
        attempts = self._failed_attempts.get(run_hash, 0) + 1
        self._failed_attempts[run_hash] = attempts
        if attempts >= self.MAX_INDEX_ATTEMPTS:
            logger.warning(f'Giving up on indexing run {run_hash} after {attempts} attempts: {reason}.')
            self._corrupted_runs.add(run_hash)
            self._stop_monitoring_chunk(run_hash)
        else:
            logger.warning(f'Indexing run {run_hash} failed ({attempts}/{self.MAX_INDEX_ATTEMPTS}): {reason}.')
            self.add_run_to_queue(run_hash)

    # Maximum number of chunk directories to watch simultaneously.
    # PollingObserver opens file descriptors for each watch; capping this
    # prevents "Too many open files" when there are hundreds of runs.
    MAX_WATCHED_CHUNKS = 50

    def monitor_chunk_directory(self, chunk_path):
        """Ensure chunk directory is monitored using a single handler."""
        if chunk_path.name not in self._watches:
            if len(self._watches) >= self.MAX_WATCHED_CHUNKS:
                # Drop the oldest watch to stay under the fd limit.
                oldest = next(iter(self._watches))
                self._stop_monitoring_chunk(oldest)
                logger.debug(f'Watch limit reached, dropped oldest watch: {oldest}')
            watch = self.chunk_change_observer.schedule(self.chunk_change_handler, chunk_path, recursive=True)
            self._watches[chunk_path.name] = watch
            logger.debug(f'Started monitoring chunk directory: {chunk_path}')
        else:
            logger.debug(f'Chunk directory already monitored: {chunk_path}')

    def add_run_to_queue(self, run_hash):
        if run_hash in self._corrupted_runs:
            return
        try:
            timestamp = os.path.getmtime(os.path.join(self.chunks_dir, run_hash))
        except FileNotFoundError:
            # The run was deleted after the change was detected; nothing left to index.
            self._stop_monitoring_chunk(run_hash)
            return
        with self.lock:
            self.indexing_queue.put((timestamp, run_hash))
        logger.debug(f'Run {run_hash} added to indexing queue with timestamp {timestamp}')

    def _process_indexing_queue(self):
        while not self._stop_event.is_set():
            _, run_hash = self.indexing_queue.get()
            logger.debug(f'Indexing run {run_hash}...')
            try:
                self.index(run_hash)
            except Exception as e:
                # An unhandled exception here would silently kill this daemon
                # thread, leaving the indexing queue permanently stalled.
                logger.error(f'Unexpected error indexing run {run_hash}: {e}')
            finally:
                self.indexing_queue.task_done()

    def index(self, run_hash):
        import gc

        if not os.path.exists(os.path.join(self.chunks_dir, run_hash)):
            # The run was deleted while it sat in the queue.
            self._stop_monitoring_chunk(run_hash)
            return True

        try:
            with self.repo.index_db_lock():
                index = self.repo._get_index_tree('meta', INDEX_DB_OPEN_TIMEOUT).view(())
                run_checksum = self._get_run_checksum(run_hash)
                meta_tree = self.repo.request_tree(
                    'meta', run_hash, read_only=True, skip_read_optimization=True
                ).subtree('meta')
                meta_run_tree = meta_tree.subtree('chunks').subtree(run_hash)
                meta_run_tree.finalize(index=index)
                index['index_cache', run_hash] = run_checksum
                self._failed_attempts.pop(run_hash, None)

                if meta_run_tree.get('end_time') is not None:
                    logger.debug(f'Indexing thread detected finished run: {run_hash}. Stopping monitoring...')
                    self._stop_monitoring_chunk(run_hash)

        except Timeout:
            # Another process holds the index db (deleting runs, reindexing). The run is
            # still outdated, so requeue it instead of dropping it as corrupted.
            logger.debug(f'Index db is busy. Postponing indexing of run {run_hash}.')
            self.add_run_to_queue(run_hash)
        except aimrocks.errors.Corruption as e:
            logger.warning(f'Indexing thread detected corrupted run: {run_hash}. Skipping. {e}')
            self._corrupted_runs.add(run_hash)
            self._stop_monitoring_chunk(run_hash)
        except aimrocks.errors.RocksIOError as e:
            # Usually contention on the index db rather than damaged data: the run is
            # intact and has to be retried, not written off.
            self._record_failure(run_hash, e)
        except Exception as e:
            # Catch-all: log and retry rather than propagating to
            # _process_indexing_queue where it would kill the thread.
            self._record_failure(run_hash, e)
        finally:
            # Release TreeView references so RocksDB containers can be GC'd
            # promptly. Without this, WeakValueDictionary entries stay alive
            # until the next GC cycle, accumulating open file descriptors.
            self.repo.container_pool.clear()
            gc.collect()
        return True

    def _is_run_index_outdated(self, run_hash, index_db):
        return self._get_run_checksum(run_hash) != index_db.get(('index_cache', run_hash))

    def _get_run_checksum(self, run_hash):
        hash_obj = hashlib.md5()

        for root, dirs, files in os.walk(os.path.join(self.chunks_dir, run_hash)):
            for name in sorted(files):  # sort to ensure consistent order
                if name.startswith('LOG'):  # skip access logs
                    continue
                filepath = os.path.join(root, name)
                try:
                    stat = os.stat(filepath)
                    hash_obj.update(filepath.encode('utf-8'))
                    hash_obj.update(str(stat.st_mtime).encode('utf-8'))
                    hash_obj.update(str(stat.st_size).encode('utf-8'))
                except FileNotFoundError:
                    # File might have been deleted between os.walk and os.stat
                    continue

        return hash_obj.hexdigest()
