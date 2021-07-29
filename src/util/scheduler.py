"""
Schedule tasks to run at a given time.
"""
import datetime as dt
import threading


class TaskNode:
    def __init__(self, value):
        self.next = None
        self.value = value
        pass


class Scheduler:
    def __init__(self):
        self.head = None
        self.active = False
        self.terminated = False
        self.timer = None
        pass

    def add_task(self, time, action, data=None):
        '''Add a task to the task-chain.
        Args:
            time (datetime): When the task occurs.
            action (function): Function to run when `time` is reached.
            data (Dict): The data associated with the task. Never used internally.
        '''
        self._handle_terminated()
        task = TaskNode({"time": time, "action": action, "data": data})
        head = self.head
        if head is None:  # First task is being added
            self.head = task
        else:
            node = self.head
            while node:
                isHead = node == self.head
                notTail = node.next != None

                afterNode = time > node.value["time"]
                if notTail:
                    beforeNextNode = time < node.next.value["time"]
                else:
                    beforeNextNode = True  # allow all times at the tail

                if afterNode and beforeNextNode:  # Add task after current node
                    task.next = node.next
                    node.next = task
                    break
                # Add task before current node (head)
                elif isHead and not afterNode:
                    task.next = node
                    self.head = task
                node = node.next

        if task == self.head:
            # Timer needs to be changed
            if self.active:
                if self.timer:
                    self.timer.cancel()
                self._wait_for_head()

    def remove_task(self, time):
        if self.head.value["time"] == time:
            self.head = self.head.next
        else:
            next_node = self.head.next
            while next_node.value["time"] != time:
                node = node.next
                next_node = node.next
            if next_node:
                node.next = next_node.next

    def clear(self):
        node = self.head
        while node:
            next_node = node.next
            del node
            node = next_node

    def _wrap_action(self, action):
        def wrapped():
            action()
            # Forget completed task
            self.head = self.head.next
            if self.active:
                self._wait_for_head()
        return wrapped

    def _wait_for_head(self):
        task = self.head
        if task:
            interval = (task.value["time"] -
                        dt.datetime.now().astimezone()).total_seconds()
            # NOTE: Negative intervals execute instantly and are allowed in threading.Timer()
            self.timer = threading.Timer(
                interval, self._wrap_action(task.value["action"]))
            self.timer.start()

    def start(self, auto_stop=False):
        '''Start the scheduler.
        Args:
            auto_stop(bool): Whether the scheduler should stop when no tasks are scheduled.
        '''
        self._handle_terminated()
        self.resume()
        if auto_stop is False:
            # Add daemon to keep scheduler alive
            self.daemon = threading.Timer(
                1 * 24 * 60 * 60, lambda: print("Exiting"))

    def terminate(self):
        '''Stop the scheduler.
        Detaches the head and marks scheduler as terminated.
        '''
        self._handle_terminated()
        self.pause()
        self.daemon.cancel()
        self.active = False
        self.terminated = True

    def _handle_terminated(self):
        if self.terminated:
            raise Exception("Can not use terminated scheduler.")

    def pause(self, timeToLast=-1):
        '''Pause the scheduler.
        Args:
            timeToLast(float, optional): Number of seconds to pause the scheduler for.
            Note that the scheduler's activity is reverted, not toggled.
        '''
        self._handle_terminated()
        self.active = False  # Does not cancel current timer
        # Remove the timer waiting for the head
        if self.timer:
            self.timer.cancel()
        if timeToLast >= 0:
            threading.Timer(timeToLast, lambda: self.resume())

    def resume(self, timeToLast=-1):
        '''Resume the scheduler.
        Args:
            timeToLast(float, optional): Number of seconds to resume the scheduler for.
            Note that the scheduler's activity is reverted, not toggled.
        '''
        self._handle_terminated()
        self.active = True
        self._wait_for_head()
        if timeToLast >= 0:
            threading.Timer(timeToLast, lambda: self.pause())
