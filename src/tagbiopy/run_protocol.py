"""Protocol execution over the FC '/t' API (the job-token flow rutherford uses).

Discovery stays on '/p' (``PRequest.get_protocols`` / ``FC.list_protocols``); this module
only adds the *execution* half, which no SDK implemented before v1.1.0:

1. POST /t ``{protocol_instance: {name, arguments}, use_cache, zip}``
   The FC replies with ONE of:
     - a finished analysis (a dict carrying ``results`` / ``protocol_instance``) -- done;
     - a plain string -- an error message;
     - a progress dict ``{token, total, count, message, results_next}`` -- a job started.
2. While the job runs, POST /t ``{token, use_cache}`` returns fresh progress.
3. When progress says ``results_next``, POST /t ``{token, results_next_received: true,
   use_cache, download?, zip?}`` returns the finished analysis (or raw bytes for
   download-type protocols).
4. POST /t ``{token, kill: true}`` aborts a running job.

Everything here is additive: '/s', '/p', '/q' behavior is untouched.
"""

import json
import time

from tagbiopy import logger
from tagbiopy.request import _Request
from tagbiopy.utils import to_json


#: How the FC marks a response as "job still running".
_PROGRESS_KEYS = {'token', 'results_next'}


class ProtocolRunError(RuntimeError):
    """The FC reported an error while running a protocol."""


class ProtocolRunTimeout(TimeoutError):
    """A protocol run exceeded the client-side timeout (the job may still be running)."""

    def __init__(self, msg, token=None):
        super().__init__(msg)
        self.token = token


class TRequest(_Request):
    """Handles '/t' API requests: submit a protocol run, poll it, fetch its results.

    Stateless per call: every method sets ``self.payload`` and issues one POST, mirroring
    the QRequest idiom. The high-level loop lives in :meth:`run`.
    """
    method_ = '/t'

    def prepare_payload(self, **kwargs) -> dict:
        ret = {k: v for k, v in kwargs.items() if v is not None}
        logger.debug(f'{self!r}: payload: {json.dumps(ret, indent=2, default=to_json)}')
        return ret

    # --- single wire calls ---------------------------------------------------------------

    def submit(self, protocol_instance, use_cache=True, zip_=False):
        """Kick off a protocol run. Returns the parsed JSON body (final, error or progress)."""
        self.payload = self.prepare_payload(
            protocol_instance=protocol_instance, use_cache=use_cache, zip=zip_)
        return self.as_dict

    def status(self, token, use_cache=True):
        """Poll a running job. Returns a progress dict."""
        self.payload = self.prepare_payload(token=token, use_cache=use_cache)
        return self.as_dict

    def results(self, token, use_cache=True, download=False, zip_=False):
        """Fetch the finished results once progress says ``results_next``.

        Returns the parsed JSON analysis for ordinary protocols, raw ``bytes`` for
        download-type protocols (``download=True``).
        """
        self.payload = self.prepare_payload(
            token=token, results_next_received=True, use_cache=use_cache,
            download=download or None, zip=zip_)
        if download:
            return self.post.content
        return self.as_dict

    def kill(self, token):
        """Abort a running job."""
        self.payload = self.prepare_payload(token=token, kill=True)
        return self.post.status_code

    # --- the loop ------------------------------------------------------------------------

    @staticmethod
    def _classify(body):
        """'final' | 'error' | 'progress' for one /t response body."""
        if isinstance(body, str):
            return 'error'
        if isinstance(body, dict) and _PROGRESS_KEYS.issubset(body.keys()):
            return 'progress'
        return 'final'

    def run(self, protocol_instance, use_cache=True, download=False, zip_=False,
            poll_interval=1.0, timeout=600, on_progress=None):
        """Run a protocol to completion. See :meth:`tagbiopy.fc.FC.run_protocol`."""
        deadline = time.monotonic() + timeout if timeout is not None else None
        body = self.submit(protocol_instance, use_cache=use_cache, zip_=zip_)
        token = None

        while True:
            kind = self._classify(body)
            if kind == 'error':
                raise ProtocolRunError(body)
            if kind == 'final':
                return body

            token = body.get('token', token)
            if on_progress is not None:
                on_progress(body)
            logger.info(
                f'{self!r}: job {token}: {body.get("count")}/{body.get("total")} '
                f'{body.get("message", "")!r}')

            if body.get('results_next'):
                if download:
                    return self.results(token, use_cache=use_cache, download=True, zip_=zip_)
                body = self.results(token, use_cache=use_cache)
                continue

            if deadline is not None and time.monotonic() > deadline:
                raise ProtocolRunTimeout(
                    f'protocol run exceeded {timeout}s (job token {token!r}; the job may '
                    f'still be running -- fetch later with TRequest.status/results or abort '
                    f'with TRequest.kill)', token=token)
            time.sleep(poll_interval)
            body = self.status(token, use_cache=use_cache)
