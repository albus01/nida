"""
@author: shawnsha@tencent.com
@date: 2016.08.08

Manage context through stack when asynchronous function called.
"""
# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, with_statement,print_function
import threading
import sys


class StackInconsistentException(Exception):
    pass

class _ContextsStack(threading.local):
    """
    The stack for contexts maintaining.
    """
    def __init__(self):
        self.contexts = (tuple(),None)
_stack = _ContextsStack()

class StackContext(object):
    """
    The container of context. Example:
        
        with StackContext(myContext):
            doSomethiingAsyn()

    Note that myContext *MUST* a callable that returns a contextmanager.
        
        @contextlib.contextmanager
        def myContext():
            try:
                yield
            except Exception as e:
                logging.error("exception %r in asynchronous function" % e)

    """

    def __init__(self, context_manager):
        self.context_manager = context_manager
        self.contexts = []
        self.active = True

    def enter(self):
        context = self.context_manager()
        self.contexts.append(context)
        context.__enter__()

    def exit(self, type, value, traceback):
        context = self.contexts.pop()
        context.__exit__(type, value, traceback)

    def _deactiveate(self):
        self.active = False

    def __enter__(self):
        self.old_stack = _stack.contexts
        self.new_stack = (_stack.contexts[0] + (self,), self)
        _stack.contexts = self.new_stack

        try:
            self.enter()
        except:
            _stack.contexts = self.old_stack
            raise

        return self._deactiveate

    def __exit__(self, type, value, traceback):
        try:
            self.exit(type, value, traceback)
        finally:
            final_stack = _stack.contexts
            _stack.contexts = self.old_stack
            if final_stack is not self.new_stack:
                raise StackInconsistentException("stack inconsistent")

            self.new_stack = None

class NullStackContext(object):
    def __enter__(self):
        self.old_stack = _stack.contexts
        _stack.contexts = (tuple(), None)

    def __exit__(self, type, value, traceback):
        _stack.contexts = self.old_stack

class ExceptionStackContext(object):
    """
    Exception handle for asynchronous function.

    Init by a exception handler.
    """
    def __init__(self, excp_handler):
        self.excp_handler = excp_handler
        self.active = True

    def _deactiveate(self):
        self.active = False

    def __enter__(self):
        #global _stack
        self.old_stack = _stack.contexts
        self.new_stack = (self.old_stack[0], self)
        _stack.contexts = self.new_stack

        return self._deactiveate

    def __exit__(self, type, value, traceback):
        #global _stack
        try:
            if type is not None:
                return self.excp_handler(type, value, traceback)
        finally:
            final_stack = _stack.contexts
            _stack.contexts = self.old_stack
            if final_stack is not self.new_stack:
                raise StackInconsistentException("stack inconsistent")

            self.new_stack = None

    def exit(self, type, value, traceback):
        if type is not None:
            return self.excp_handler(type, value, traceback)

def _delete_inactive_context(contexts):
    """
    To remove the deactive context in the context stack.
    """
    #clean contexts in stack
    stack_contexts = tuple(context for context in contexts[0] if context.active)
    
    #find new active head
    head = contexts[1]
    while head is not None and not head.active:
        head = head.old_stack[1]

    active_head = head
    while active_head is not None:
        parent = active_head.old_stack[1]
        while parent is not None:
            if parent.active:
                break
            parent = parent.old_stack[1]
            active_head.old_stack = parent.old_stack
        active_head = parent

    return (stack_contexts, head)

def wrap(func):
    """
    Return a wrapped function that capture the current context when excuted.
    """
    if func is None or hasattr(func, '_has_wrapped'):
        return func
    
    cap_stack = [_stack.contexts]
    if not cap_stack[0][0] and not cap_stack[0][1]:
        def null_wrapper(*args, **kwargs):
            try:
                #Note that cap_stack is the correct context who is borned when func wrapped.
                #But there may be some other context join in between the
                #wrapped func is called and context capture.
                current_contexts = _stack.contexts
                _stack.contexts = cap_stack[0]
                func(*args, **kwargs)
            finally:
                #should recover the contexts that join in between wrapped func
                #is called and context capture.
                _stack.contexts = current_contexts

        null_wrapper._has_wrapped = True
        return null_wrapper
    
    def wrapped(*args, **kwargs):
        ret = None
        try:
            excp = (None, None, None)
            top = None
            current_contexts = _stack.contexts
            """Note:
                *_stack.contexts* = contexts = _delete_inactive_context(cap_stack[0])

                Should give *_stack.contexts* last captured contexts because
                contexts which in the _stack will exit when 'with' block come
                to the end. And there will be asynchronous context join at the
                same time in the 'with' block, so shuold let the new context
                know its above contexts when '__enter__()'.

                example:
                def f1(name):
                    with StackContext(partial(context,'a')):
                        _loop.add_callback(f2, name)

                def f2(name):
                    with StackContext(partial(context, 'b')):
                        _loop.add_callback(f3)

                def f3():
                   raise Exception("f3 exception")

                _loop.add_callback(f2, name) will capture the current contexts
                and return wrapped func, when wrapped(), it should give
                *_stack.contexts* the captureed contexts so that 'with
                StackContext(partial(context,'b'))' will know its above
                contexts when `__enter__()`. If not, the exception can only
                transfer to f2's context cause it has losed its context chain.

            """
            _stack.contexts = contexts = _delete_inactive_context(cap_stack[0])
            #contexts = _delete_inactive_context(cap_stack[0])
            stack = contexts[0]
            context_count = 0
            for context in stack:
                try:
                    context.enter()
                    context_count += 1
                except:
                    top = context.old_stack[1]
                    excp = sys.exc_info()

            if top is None:
                try:
                    ret = func(*args, **kwargs)
                except:
                    top = contexts[1]
                    excp = sys.exc_info()

            if top is not None:
                excp = _handle_excp(top, excp)
            else:
                while context_count > 0:
                    context_count -= 1
                    try:
                        stack = contexts[0][context_count]
                        stack.exit(*excp)
                    except:
                        excp = sys.exc_info()
                        top = stack.old_stack[1]
                        excp = _handle_excp(top, excp)
                        break

            if excp != (None, None, None):
                raise excp[0], excp[1], excp[2]
        finally:
            _stack.contexts = current_contexts
        return ret
    
    wrapped._has_wrapped = True
    return wrapped

def _handle_excp(top, excp):
    """
    Handle exception through context stack top chain.
    """
    while top is not None:
        try:
            if top.exit(*excp):
                excp = (None, None, None)
        except:
            excp = sys.exc_info()

        top = top.old_stack[1]

    return excp



