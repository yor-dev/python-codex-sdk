"""
Codex main class for interacting with the Codex agent.
"""

from .codex_options import CodexOptions
from .exec import CodexExec
from .thread import Thread
from .thread_options import ThreadOptions


class Codex:
    """
    Codex is the main class for interacting with the Codex agent.

    Use the startThread() method to start a new thread or resumeThread() to resume a previously started thread.
    """

    def __init__(self, options: CodexOptions | None = None):
        """
        Initialize a Codex instance.

        Args:
            options: Optional Codex configuration options
        """
        if options is None:
            options = CodexOptions()

        self._exec = CodexExec(
            executable_path=options.codex_path_override,
            env=options.env,
        )
        self._options = options

    def start_thread(self, options: ThreadOptions | None = None) -> Thread:
        """
        Start a new conversation with an agent.

        Args:
            options: Optional thread-specific options

        Returns:
            A new Thread instance
        """
        if options is None:
            options = ThreadOptions()

        return Thread(self._exec, self._options, options)

    def resume_thread(self, id: str, options: ThreadOptions | None = None) -> Thread:
        """
        Resume a conversation with an agent based on the thread id.
        Threads are persisted in ~/.codex/sessions.

        Args:
            id: The id of the thread to resume
            options: Optional thread-specific options

        Returns:
            A new Thread instance
        """
        if options is None:
            options = ThreadOptions()

        return Thread(self._exec, self._options, options, id)
