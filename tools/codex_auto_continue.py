"""Continue a loaded Codex thread after a terminal HTTP 429/503 failure.

Requires a reachable *existing* app-server control socket. Does not launch a new
server, resume/unload threads, approve tools, or inspect prompt content.
Python standard library only. See docs/codex_auto_continue.md.
"""
import argparse
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid


STATUS = re.compile(
    r'\b(?:http(?:/\d(?:\.\d)?)?\s+|(?:http[_ ]?)?status(?:[_ ]?code)?["\s:=]+)([45]\d{2})\b'
    r'|\b(429)\s+Too Many Requests\b|\b(503)\s+Service Unavailable\b', re.I
)


def error_codes(error):
    if not isinstance(error, dict):
        return set()
    codes = set()
    for key, value in error.items():
        if key in {'httpStatusCode', 'status_code', 'http_status_code'} and isinstance(value, int):
            codes.add(value)
        elif isinstance(value, dict):
            codes.update(error_codes(value))
        elif key in {'message', 'additionalDetails'} and isinstance(value, str):
            for match in STATUS.finditer(value):
                codes.update(int(part) for part in match.groups() if part)
    return codes


def candidate(thread, codes):
    # Active includes the built-in retry loop and waiting for approval/input.
    if thread.get('status', {}).get('type') not in {'idle', 'systemError'}:
        return None
    turns = thread.get('turns') or []
    if not turns or turns[-1].get('status') != 'failed':
        return None
    turn = turns[-1]
    matches = error_codes(turn.get('error')) & codes
    if matches and turn.get('id'):
        return turn['id'], min(matches)
    return None


class State:
    def __init__(self, path, thread_id):
        self.path = path
        self.data = {'thread_id': thread_id, 'attempts': 0, 'handled': []}
        if path.exists():
            self.data = json.loads(path.read_text(encoding='utf-8'))
            if self.data.get('thread_id') != thread_id:
                raise ValueError('State belongs to another thread')
            if not isinstance(self.data.get('attempts'), int) or not isinstance(self.data.get('handled'), list):
                raise ValueError('Invalid watcher state')

    def allowed(self, turn_id, limit):
        return turn_id not in self.data['handled'] and self.data['attempts'] < limit

    def reserve(self, turn_id):
        # Persist BEFORE sending: an ambiguous transport failure must not cause
        # the next process to send the same continuation a second time.
        self.data['handled'].append(turn_id)
        self.data['attempts'] += 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')
        temporary.replace(self.path)


class Rpc:
    def __init__(self, executable, socket_path=None):
        command = [executable, 'app-server', 'proxy']
        if socket_path:
            command += ['--sock', socket_path]
        self.process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        self.messages = queue.Queue()
        self.next_id = 0
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            for line in self.process.stdout:
                self.messages.put(json.loads(line))
        except (ValueError, OSError) as error:
            self.messages.put(error)
        finally:
            self.messages.put(None)

    def send(self, message):
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + '\n')
        self.process.stdin.flush()

    def call(self, method, params, timeout=15):
        self.next_id += 1
        request_id = self.next_id
        self.send({'id': request_id, 'method': method, 'params': params})
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f'{method}: response timeout; delivery may be uncertain')
            try:
                message = self.messages.get(timeout=remaining)
            except queue.Empty:
                raise RuntimeError(f'{method}: response timeout; delivery may be uncertain') from None
            if message is None or isinstance(message, Exception):
                raise RuntimeError('Cannot communicate with the existing Codex app-server control socket')
            if message.get('id') != request_id or 'method' in message:
                # Never answer approval/input requests or use assistant text as status.
                continue
            if 'error' in message:
                raise RuntimeError(f'{method} rejected (RPC code {message["error"].get("code")})')
            return message['result']

    def initialize(self):
        self.call('initialize', {'clientInfo': {'name': 'codex-auto-continue', 'version': '1.0'}})
        self.send({'method': 'initialized'})

    def read_thread(self, thread_id):
        return self.call('thread/read', {'threadId': thread_id, 'includeTurns': True})['thread']

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process.stdin.close()
        self.process.stdout.close()


def lock_thread(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open('a+b')
    handle.write(b'0')
    handle.flush()
    handle.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError('Another watcher is already monitoring this thread') from None
    return handle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--thread', required=True, type=lambda value: str(uuid.UUID(value)))
    parser.add_argument('--codex', default=shutil.which('codex'))
    parser.add_argument('--socket', help='Existing desktop/shared app-server control socket')
    parser.add_argument('--check', action='store_true', help='Read status once; never send a message')
    parser.add_argument('--interval', type=float, default=10)
    parser.add_argument('--cooldown', type=float, default=60)
    parser.add_argument('--max-retries', type=int, default=3)
    args = parser.parse_args()
    if not args.codex or args.interval <= 0 or args.cooldown < 1 or args.max_retries < 1:
        parser.error('codex must exist; interval, cooldown and max-retries must be positive')
    codex_dir = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
    state_path = codex_dir / 'auto-continue' / f'{args.thread}.json'
    rpc = None
    lock = None
    try:
        if not args.check:
            lock = lock_thread(state_path.with_suffix('.lock'))
        state = State(state_path, args.thread)
        rpc = Rpc(args.codex, args.socket)
        rpc.initialize()
        print(f'Connected. Monitoring thread {args.thread}; HTTP 429/503 only.', flush=True)
        while True:
            thread = rpc.read_thread(args.thread)
            runtime = thread.get('status', {}).get('type')
            if args.check:
                print(json.dumps({'thread': args.thread, 'runtime': runtime,
                                  'candidate': candidate(thread, {429, 503})}), flush=True)
                return 0
            if runtime == 'notLoaded':
                raise RuntimeError('Thread is not loaded on this server; open it in the matching Codex app first')
            found = candidate(thread, {429, 503})
            if found:
                turn_id, code = found
                if not state.allowed(turn_id, args.max_retries):
                    print('Stopped: this failure was already handled or the retry limit was reached.', flush=True)
                    return 0
                delay = min(args.cooldown * (2 ** min(state.data['attempts'], 10)), 900)
                print(f'HTTP {code}; failed turn {turn_id}. Rechecking in {delay:g}s.', flush=True)
                time.sleep(delay)
                # A user may have resumed, interrupted, or completed work meanwhile.
                if candidate(rpc.read_thread(args.thread), {429, 503}) != found:
                    continue
                state.reserve(turn_id)
                result = rpc.call('turn/start', {'threadId': args.thread,
                    'input': [{'type': 'text', 'text': '\u7ee7\u7eed', 'text_elements': []}]})
                print(f'Continuation accepted: turn {result.get("turn", {}).get("id", "unknown")}', flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print('Watcher stopped.', file=sys.stderr)
        return 0
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f'Watcher stopped: {error}. No automatic resend will be attempted.', file=sys.stderr)
        return 1
    finally:
        if rpc:
            rpc.close()
        if lock:
            lock.close()


if __name__ == '__main__':
    sys.exit(main())
