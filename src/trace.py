import logging
import time
import uuid
from contextlib import contextmanager


class TraceNode:
    def __init__(self, name, parent=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.parent = parent
        self.children = []
        self.start_time = time.time()
        self.end_time = None
        self.status = "running"
        self.metadata = {}


class Tracer:
    def __init__(self):
        self.current_span = None
        self.logger = logging.getLogger("trace")
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)
            self.logger.propagate = False
            self.logger.setLevel(logging.INFO)

    @contextmanager
    def span(self, name, **kwargs):
        node = TraceNode(name, parent=self.current_span)
        if self.current_span:
            self.current_span.children.append(node)
        node.metadata.update(kwargs)

        prev_span = self.current_span
        self.current_span = node

        try:
            yield node
            node.status = "success"
        except Exception as e:
            node.status = "error"
            node.metadata["error"] = str(e)
            raise
        finally:
            node.end_time = time.time()
            self.current_span = prev_span
            self._log_span(node)

    def _log_span(self, node: TraceNode):
        duration = node.end_time - node.start_time if node.end_time else 0
        indent = "  " * self._get_depth(node)
        status_mark = "✓" if node.status == "success" else "✗"
        self.logger.info(f"{indent}{status_mark} [{node.name}] ({duration:.3f}s)")

    def _get_depth(self, node: TraceNode):
        depth = 0
        curr = node.parent
        while curr:
            depth += 1
            curr = curr.parent
        return depth


tracer = Tracer()
