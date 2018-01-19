#
#    Copyright (C) 2017 Kenneth A. Giusti
#
#    Licensed to the Apache Software Foundation (ASF) under one
#    or more contributor license agreements.  See the NOTICE file
#    distributed with this work for additional information
#    regarding copyright ownership.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#

import abc
import json
import logging
import math
import os
import socket
import threading
import time
from time import time as now
try:
    import Queue as queue
except ImportError:
    import queue
import oslo_messaging as om
import uuid


__all__ = [
    "RPCTestClient",
    "RPCTestServer",
    "TestNotifier",
    "TestListener",
    "Controller"
]

# the types of oslo.messaging clients
RPC_CLIENT = 'RPCClient'
RPC_SERVER = 'RPCServer'
LISTENER = 'Listener'
NOTIFIER = 'Notifier'
MESSAGING_CLIENT_TYPES = [RPC_CLIENT, RPC_SERVER, LISTENER, NOTIFIER]

# addressing for control messages
CONTROL_EXCHANGE = 'ombt-control'
CONTROLLER_TOPIC = 'controller-%s'
CLIENT_TOPIC = "client-%s-%s"    # client-$type-$topic

# addressing for RPC tests
RPC_EXCHANGE = 'ombt-rpc-test'
RPC_TOPIC = "rpc-%s"

# addressing for Notification tests
NOTIFY_EXCHANGE = 'ombt-notify-test'
NOTIFY_TOPIC = "notify-%s"


def _wait_stabilize(delay, count_fn):
    # helper to wait until a counter has stabilized for delay seconds
    count = count_fn()
    timeout = delay
    while timeout > 0:
        time.sleep(1.0)
        new_count = count_fn()
        if count != new_count:
            # reset
            count = new_count
            timeout = delay
        else:
            timeout -= 1


class Stats(object):
    """Manage a single statistic"""
    def __init__(self, min=None, max=None, total=0, count=0,
                 sum_of_squares=0, distribution=None):
        self.min = min
        self.max = max
        self.total = total
        self.count = count
        self.sum_of_squares = sum_of_squares
        # distribution of values grouped by powers of 10
        self.distribution = distribution or dict()

    @classmethod
    def from_dict(cls, values):
        if 'distribution' in values:
            # hack alert!
            # when a Stats is passed via an RPC call it appears as if the
            # distribution map's keys are converted from int to str.
            # Fix that by re-indexing the distribution map:
            new_dict = dict()
            old_dict = values['distribution']
            for k in old_dict.keys():
                new_dict[int(k)] = old_dict[k]
            values['distribution'] = new_dict
        return Stats(**values)

    def to_dict(self):
        new_dict = dict()
        for a in ["min", "max", "total", "count", "sum_of_squares"]:
            new_dict[a] = getattr(self, a)
        new_dict["distribution"] = self.distribution.copy()
        return new_dict

    def update(self, value):
        self.total += value
        self.count += 1
        self.sum_of_squares += value**2
        self.min = min(self.min, value) if self.min else value
        self.max = max(self.max, value) if self.max else value
        log = int(math.log10(value)) if value >= 1.0 else 0
        base = 10**log
        index = int(value / base)  # 0..9
        if log not in self.distribution:
            self.distribution[log] = [0 for i in range(10)]
        self.distribution[log][index] += 1

    def reset(self):
        self.__init__()

    def average(self):
        return (self.total / float(self.count)) if self.count else 0

    def std_deviation(self):
        return math.sqrt((self.sum_of_squares / float(self.count)) -
                         (self.average() ** 2)) if self.count else -1

    def merge(self, stats):
        if stats.min is not None and self.min is not None:
            self.min = min(self.min, stats.min)
        else:
            self.min = self.min or stats.min
        if stats.max is not None and self.max is not None:
            self.max = max(self.max, stats.max)
        else:
            self.max = self.max or stats.max

        self.total += stats.total
        self.count += stats.count
        self.sum_of_squares += stats.sum_of_squares
        for k in stats.distribution.keys():
            if k in self.distribution:
                self.distribution[k] = [z for z in map(lambda a, b: a + b,
                                                       stats.distribution[k],
                                                       self.distribution[k])]
            else:
                self.distribution[k] = stats.distribution[k]

    def __str__(self):
        return "min=%i, max=%i, avg=%f, std-dev=%f" % (self.min, self.max,
                                                       self.average(),
                                                       self.std_deviation())

    def print_distribution(self):
        keys = list(self.distribution.keys())
        keys.sort()
        for order in keys:
            row = self.distribution[order]
            # order=0, index=0 is special case as it is < 1.0, for all orders >
            # 0, index 0 is ignored since everthing < 10^order is accounted for
            # in index 9 of the (order - 1) row
            index = 0 if order == 0 else 1
            while index < len(row):
                print("[%d..<%d):  %d" %
                      ((10 ** int(order)) * index,
                       (10 ** int(order)) * (index + 1),
                       row[index]))
                index += 1


class NullOutputter(object):
    """ Output handler used if no output is desired
    """

    def write(self, msg):
        pass


class FileOutputter(object):
    """Output handler used for sending output to a file
    """

    def __init__(self, filepath):
        self._fobj = open(filepath, 'w', -1)

    def write(self, msg):
        self._fobj.write(msg)


class TestResults(object):
    """Client results of a test run.
    """

    def __init__(self, start_time=None, stop_time=None, latency=None,
                 msgs_ok=0, msgs_fail=0, errors=None):
        super(TestResults, self).__init__()
        self.start_time = start_time
        self.stop_time = stop_time
        self.latency = latency or Stats()
        self.msgs_ok = msgs_ok  # count of successful msg transfers
        self.msgs_fail = msgs_fail  # count of failed msg transfers
        self.errors = errors or dict()  # error msgs and counts

    @classmethod
    def from_dict(cls, values):
        if 'latency' in values:
            values['latency'] = Stats.from_dict(values['latency'])
        if 'errors' in values:
            values['errors'] = values['errors'].copy()
        return TestResults(**values)

    def to_dict(self):
        new_dict = dict()
        for a in ['start_time', 'stop_time', 'msgs_ok', 'msgs_fail']:
            new_dict[a] = getattr(self, a)
        new_dict['latency'] = self.latency.to_dict()
        new_dict['errors'] = self.errors.copy()
        return new_dict

    def error(self, reason):
        key = str(reason)
        self.errors[key] = self.errors.get(key, 0) + 1

    def reset(self):
        self.__init__()

    def merge(self, results):
        self.start_time = (min(self.start_time, results.start_time)
                           if self.start_time and results.start_time
                           else (self.start_time or results.start_time))
        self.stop_time = (max(self.stop_time, results.stop_time)
                          if self.stop_time and results.stop_time
                          else (self.stop_time or results.stop_time))
        self.msgs_ok += results.msgs_ok
        self.msgs_fail += results.msgs_fail
        self.latency.merge(results.latency)
        for err in results.errors:
            self.errors[err] = self.errors.get(err, 0) + results.errors[err]

    def print_results(self):
        if self.msgs_fail:
            print("Error: %d message transfers failed"
                  % self.msgs_fail)
        if self.errors:
            print("Error: errors detected:")
            for err in self.errors:
                print("  '%s' (occurred %d times)" % (err, self.errors[err]))

        total = self.msgs_ok + self.msgs_fail
        print("Total Messages: %d" % total)

        delta_time = self.stop_time - self.start_time
        print("Test Interval: %f - %f (%f secs)" % (self.start_time,
                                                    self.stop_time,
                                                    delta_time))

        if delta_time > 0.0:
            print("Aggregate throughput: %f msgs/sec" %
                  (float(total) / delta_time))

        latency = self.latency
        if latency.count:
            print("Latency %d samples (msecs): Average %f StdDev %f"
                  " Min %f Max %f"
                  % (latency.count,
                     latency.average(), latency.std_deviation(),
                     latency.min, latency.max))
            print("Latency Distribution: ")
            latency.print_distribution()


class _Base(object):
    """Common base for all ombt2 processes.  Establishes a connection to the
    control message bus and a subscription for control messages
    """

    def __init__(self, cfg, ctl_url, topic, output, name, unique=False,
                 kind=None, timeout=None):
        super(_Base, self).__init__()
        self._finished = threading.Event()

        self._timeout = timeout
        if kind is None:
            ctl_topic = CONTROLLER_TOPIC % (topic
                                            if not unique else 'singleton')
            self.kind = "Controller"
        else:
            ctl_topic = CLIENT_TOPIC % ((kind, topic)
                                        if not unique else (kind, 'singleton'))
            self.kind = kind

        self.name = name or 'ombt-%s-%s-%s-%s-%s' % (topic,
                                                     kind,
                                                     socket.gethostname(),
                                                     os.getpid(),
                                                     uuid.uuid4().hex)
        self.ctl_url = ctl_url
        self.ctl_tport = om.get_rpc_transport(cfg.CONF,
                                              url=ctl_url)
        # My address and subscription for receiving control commands/responses
        self.ctl_target = om.Target(exchange=CONTROL_EXCHANGE,
                                    topic=ctl_topic,
                                    server=self.name)
        self._ctl_server = om.get_rpc_server(self.ctl_tport,
                                             target=self.ctl_target,
                                             endpoints=[self],
                                             executor="threading")
        self._ctl_server.start()

        if output is not None:
            try:
                self._output = FileOutputter(output)
            except Exception as exc:
                logging.error("Cannot open output file %s: %s!",
                              output, str(exc))
                self._output = NullOutputter()
        else:
            self._output = NullOutputter()

    def start(self):
        # blocks until connection to the control bus is active
        ready = False
        attempts = 0
        logging.debug("%s connecting to the control message bus...", self.name)
        # call my "self_ready" method until it returns successfully.
        # this indicates the connection to the control bus is active.
        client = om.RPCClient(self.ctl_tport,
                              target=self.ctl_target,
                              timeout=2)
        while not ready and attempts < 25:
            try:
                ready = client.call({}, 'self_ready')
            except om.MessagingTimeout:
                attempts += 1
        if not ready:
            raise Exception("Unable to contact message bus")
        logging.debug("%s is listening", self.name)

    def wait(self, timeout=None):
        # blocks until client completes shutdown
        return self._finished.wait(timeout)

    def _do_shutdown(self):
        self._ctl_server.stop()
        self._ctl_server.wait()
        self._finished.set()
        logging.debug("%s has shut down", self.name)

    #
    # RPC calls:
    #

    def shutdown(self, ctxt):
        # cannot synchronously shutdown server since this call is dispatched by
        # the server...
        threading.Thread(target=self._do_shutdown).start()

    def self_ready(self, ctxt):
        # simple ping to determine when message bus is connected
        return True


class _Client(_Base):
    """Common base for non-controller clients.  Defines RPC calls that are
    invoked by the Controller to control the tests.
    """
    def __init__(self, cfg, ctl_url, topic, kind, timeout, name,
                 unique=False, output=None):
        # listen on 'client-$topic' for controller commands:
        super(_Client, self).__init__(cfg, ctl_url, topic, output, name,
                                      unique, kind, timeout)
        self.topic = CLIENT_TOPIC % ((kind, topic)
                                     if not unique else (kind, 'singleton'))
        self.results = TestResults()
        self._results_lock = threading.Lock()
        self._output.write('{"client-name": "%(client)s",'
                           ' "kind": "%(kind)s"}\n'
                           % {'client': self.name,
                              'kind': kind})

    #
    # RPC Calls
    #

    def client_ping(self, ctxt, reply_addr):
        # invoked by controller via rpc-cast to roll-call available clients
        logging.debug("Client ping received (%s)", self.name)
        target = om.Target(**reply_addr)
        ctrl = om.RPCClient(self.ctl_tport, target=target,
                            timeout=self._timeout)
        try:
            ctrl.call({}, "client_pong", kind=self.kind, name=self.name)
        except Exception as exc:
            err = str(exc)
            logging.error("client pong call failed: %s", err)
            self.error(err)
        else:
            logging.debug("Client pong sent (%s) (%s)", self.name, target)


class _TestClient(_Client):
    """Base class for Notifier and RPC clients
    """
    def __init__(self, cfg, ctl_url, topic, kind, name, timeout, unique=False,
                 output=None):
        super(_TestClient, self).__init__(cfg, ctl_url, topic, kind, timeout,
                                          name, unique, output)

    # helper to execute func(timestamp) count times, pausing pause seconds
    # between invocation.  Provides extra logging if verbose
    def _execute(self, func, count=0, pause=0, verbose=False):
        stop = False
        msgid = uuid.uuid4().hex
        seq = 0
        self.results.start_time = now()
        while not stop:
            err = None
            ts = now()
            try:
                func(ts, "%s:%d" % (msgid, seq))
            except Exception as exc:
                self.results.msgs_fail += 1
                err = str(exc)
                self.results.error(err)
                logging.error("Test client failed to send message: %s", err)
            else:
                self.results.msgs_ok += 1
            done = now()
            self.results.latency.update((done - ts) * 1000)
            self._output.write('{"id": "%(msgid)s", "start": %(start)f,'
                               ' "stop": %(stop)f%(error)s}\n'
                               % {'msgid': "%s:%d" % (msgid, seq),
                                  'start': ts,
                                  'stop': done,
                                  'error':
                                  (', "error": "%s"' % err) if err else ""
                                  }
                               )
            seq += 1
            if pause:
                time.sleep(pause)
            if count and self.results.latency.count >= count:
                stop = True
        self.results.stop_time = now()

    #
    # RPC Calls
    #

    @abc.abstractmethod
    def run_test(self, ctxt, test, kwargs, reply_addr):
        """Called by the controller to have the client run test 'test' with
        arguments kwargs. When the test completes the client sends the results
        to the controller at 'reply_addr' by calling its 'client_result'
        method.  Note: this is an RPC method that is invoked by the test
        controller via a fanout 'cast' - not 'call' (the controller does not
        block for results)
        """


class _TestServer(_Client):
    """Base class for Listener and RPC servers
    """
    def __init__(self, cfg, ctl_url, topic, kind, name, timeout, unique=False,
                 output=None):
        super(_TestServer, self).__init__(cfg, ctl_url, topic, kind, timeout,
                                          name, unique, output)

    #
    # Controller RPC Calls
    #
    def get_server_results(self, ctxt, reply_addr):
        """Called by the controller to gather server side test data.  May be
        called repeatedly until the test completes.  Note this is invoked by
        the controller via a fanout 'cast' - not a 'call' (the controller does
        not block for results)
        """
        with self._results_lock:
            results = self.results.to_dict()
            self.results.reset()

        controller = om.RPCClient(self.ctl_tport,
                                  om.Target(**reply_addr),
                                  timeout=self._timeout)
        try:
            controller.call({}, 'client_result', name=self.name,
                            kind=self.kind, results=results)
        except Exception as exc:
            # I don't think recovery is possible as the call may be in-doubt.
            # For now simply let folks know the results may be invalid
            err = str(exc)
            logging.error("%s failed to report results!"
                          " Test results may be invalid!"
                          " Error: %s", err)
        else:
            logging.debug("Server %s test results sent", self.name)


class RPCTestClient(_TestClient):
    """Runs the RPC tests against the RPCTestServer
    """
    def __init__(self, cfg, ctl_url, test_url, topic, name, timeout,
                 unique=False, output=None):
        super(RPCTestClient, self).__init__(cfg, ctl_url, topic, RPC_CLIENT,
                                            name, timeout, unique, output)
        # for calling the test RPC server(s):
        target = om.Target(exchange=RPC_EXCHANGE,
                           topic=RPC_TOPIC % topic)
        fanout_target = om.Target(exchange=RPC_EXCHANGE,
                                  topic=RPC_TOPIC % topic,
                                  fanout=True)
        tport = (self.ctl_tport
                 if test_url == self.ctl_url
                 else om.get_rpc_transport(cfg.CONF, url=test_url))
        self._rpc_client = om.RPCClient(tport,
                                        target=target,
                                        timeout=timeout)
        self._fanout_client = om.RPCClient(tport,
                                           target=fanout_target,
                                           timeout=timeout)
    #
    # RPC Calls:
    #

    def run_test(self, ctxt, test, kwargs, reply_addr):
        func = None
        verbose = kwargs.get("verbose", False)
        pause = kwargs.get("pause", 0)
        data = kwargs.get("data", "")
        count = kwargs.get("count", 0)

        if test == "test_call":
            func = lambda ts, msgid: self._rpc_client.call({}, 'echo',
                                                           data=data,
                                                           timestamp=ts,
                                                           msgid=msgid)
        elif test == "test_cast":
            func = lambda ts, msgid: self._rpc_client.cast({}, 'noop',
                                                           data=data,
                                                           timestamp=ts,
                                                           msgid=msgid)
        elif test == "test_fanout":
            func = lambda ts, msgid: self._fanout_client.cast({}, 'noop',
                                                              data=data,
                                                              timestamp=ts,
                                                              msgid=msgid)
        else:
            logging.error("Client %s ignoring unknown test %s",
                          self.name, test)
            return

        self._output.write('{"test-name": "%(name)s",'
                           ' "test-start": %(start)f}\n'
                           % {'name': test, 'start': now()})

        controller = om.RPCClient(self.ctl_tport,
                                  om.Target(**reply_addr),
                                  timeout=self._timeout)
        logging.debug("Client %s starting test %s ...", self.name, test)

        # Before running the test, try to ping the server.  This will force a
        # link setup so the first latency-timed message will not be blocked
        # waiting for the setup to complete.
        try:
            self._rpc_client.call({}, "self_ready")
        except Exception as exc:
            logging.warning("Client %s is unable to reach RPC server: %s",
                            self.name, str(exc))
            self.results.error(str(exc))
            # keep going, perhaps the test will not fail...

        self._execute(func, count, pause, verbose)

        self._output.write('{"test-end": %f}\n' % now())

        logging.debug("Client %s test %s finished, sending results...",
                      self.name, test)
        try:
            controller.call({}, 'client_result', name=self.name,
                            kind=self.kind, results=self.results.to_dict())
        except Exception as exc:
            # I don't think recovery is possible as the call may be in-doubt.
            # For now simply let folks know the results may be invalid
            logging.error("%s failed to report results!"
                          " Test results may be invalid!"
                          " Error: %s", RPC_CLIENT, str(exc))
        else:
            logging.debug("Client %s test %s results sent", self.name, test)
        self.results.reset()


class RPCTestServer(_TestServer):
    """Response to RPC requests from RPCTestClient
    """
    def __init__(self, cfg, ctl_url, test_url, topic, executor, name, timeout,
                 unique=False, output=None):
        super(RPCTestServer, self).__init__(cfg, ctl_url, topic, RPC_SERVER,
                                            name, timeout, unique, output)
        target = om.Target(exchange=RPC_EXCHANGE,
                           topic=RPC_TOPIC % topic,
                           server=self.name)
        tport = (self.ctl_tport
                 if test_url == self.ctl_url
                 else om.get_rpc_transport(cfg.CONF, url=test_url))
        self._rpc_server = om.get_rpc_server(tport,
                                             target,
                                             [self],
                                             executor=executor)
        self._rpc_server.start()

    def _update_stats(self, timestamp, msgid):
        # given timestamp from arriving message
        ts = now()
        self._output.write('{"id": "%s", "start": %f, "recv": %f'
                           % (msgid, timestamp, ts))

        if timestamp > ts:
            logging.error("Clock error detected:"
                          " send time (%f) after arrival time (%f)"
                          " test results will be invalid!",
                          timestamp, ts)
            with self._results_lock:
                self.results.error("Clocks not synchronized")
                self.results.msgs_fail += 1
            self._output.write(', "error": "unsynchronized clocks"\n')
        else:
            with self._results_lock:
                self.results.start_time = (min(self.results.start_time, ts)
                                           if self.results.start_time else ts)
                self.results.stop_time = (max(self.results.stop_time, ts)
                                          if self.results.stop_time else ts)
                self.results.msgs_ok += 1
                self.results.latency.update((ts - timestamp) * 1000)
        self._output.write('}\n')

    #
    # Controller RPC Calls:
    #

    def shutdown(self, ctxt):
        self._rpc_server.stop()
        self._rpc_server.wait()
        super(RPCTestServer, self).shutdown(ctxt)

    #
    # Test RPC Calls:
    #

    def noop(self, ctxt, data, timestamp, msgid):
        # for cast testing - called by RPCTestClient, no return value
        self._update_stats(timestamp, msgid)
        logging.debug("RPCServer.noop(timestamp=%s)", timestamp)

    def echo(self, ctxt, data, timestamp, msgid):
        # for call testing - called by RPCTestClient
        self._update_stats(timestamp, msgid)
        logging.debug("RPCServer.echo(timestamp=%s)", timestamp)
        return data


class TestNotifier(_TestClient):
    """Client for issuing Notification calls to the TestListener
    """
    def __init__(self, cfg, ctl_url, test_url, topic, name, timeout,
                 output=None):
        super(TestNotifier, self).__init__(cfg,
                                           ctl_url,
                                           topic,
                                           NOTIFIER,
                                           name,
                                           timeout,
                                           output)
        # for notifying the test listener:
        om.set_transport_defaults(control_exchange=NOTIFY_EXCHANGE)
        tport = om.get_notification_transport(cfg.CONF, url=test_url)
        topic = NOTIFY_TOPIC % topic
        self._notifier = om.notify.notifier.Notifier(tport,
                                                     self.name,
                                                     driver='messaging',
                                                     topics=[topic])
    #
    # RPC Calls:
    #

    def run_test(self, ctxt, test, kwargs, reply_addr):
        if test != 'test_notify':
            # ignore other tests, like rpc-call, etc
            return
        verbose = kwargs.get("verbose", False)
        pause = kwargs.get("pause", 0)
        data = kwargs.get("data", "")
        count = kwargs.get("count", 0)
        severity = kwargs.get("severity", "debug")

        controller = om.RPCClient(self.ctl_tport,
                                  om.Target(**reply_addr),
                                  timeout=self._timeout)
        logging.debug("Client %s starting test %s ...", self.name, test)

        func = getattr(self._notifier, severity)
        payload = {'payload': data}

        def test_func(timestamp, msgid):
            payload['timestamp'] = timestamp
            payload['msgid'] = msgid
            func({}, "notification-test", payload)

        self._output.write('{"test-name": "test_notify",'
                           ' "test-start": %(start)f}\n'
                           % {'start': now()})

        self._execute(test_func, count, pause, verbose)

        self._output.write('{"test-end": %f}\n' % now())

        logging.debug("Client %s test %s finished, sending results...",
                      self.name, test)

        with self._results_lock:
            results = self.results.to_dict()
            self.results.reset()

        try:
            controller.call({}, 'client_result', name=self.name,
                            kind=self.kind, results=results)
        except Exception as exc:
            # I don't think recovery is possible as the call may be in-doubt.
            # For now simply let folks know the results may be invalid
            logging.error("%s failed to report results!"
                          " Test results may be invalid!"
                          " Error: %s", str(exc))
        else:
            logging.debug("Client %s test %s results sent", self.name, test)


class TestListener(_TestServer):
    def __init__(self, cfg, ctl_url, test_url, topic, executor, name, timeout,
                 pool=None, output=None):
        super(TestListener, self).__init__(cfg,
                                           ctl_url,
                                           topic,
                                           LISTENER,
                                           name,
                                           timeout, output)
        target = om.Target(exchange=NOTIFY_EXCHANGE,
                           topic=NOTIFY_TOPIC % topic,
                           server=self.name)
        om.set_transport_defaults(control_exchange=NOTIFY_EXCHANGE)
        tport = om.get_notification_transport(cfg.CONF, url=test_url)
        self._listener = om.get_notification_listener(tport,
                                                      [target],
                                                      [self],
                                                      executor=executor,
                                                      pool=pool)
        self._listener.start()

    #
    # Controller RPC Calls:
    #

    def shutdown(self, ctxt):
        self._listener.stop()
        self._listener.wait()
        super(TestListener, self).shutdown(ctxt)

    #
    # Notifications:
    #

    def _report(self, severity, ctx, publisher, event_type, payload, metadata):
        ts = now()
        logging.debug("%s Notification %s:%s:%s:%s:%s", self.name, severity,
                      publisher, event_type, payload, metadata)

        timestamp = payload['timestamp']
        msgid = payload['msgid']

        self._output.write('{"id": "%(msgid)s", "start": %(start)f,'
                           ' "recv": %(recv)f'
                           % {'msgid': msgid, 'start': timestamp, 'recv': ts})

        if timestamp > ts:
            logging.error("Clock error detected:"
                          " send time (%f) after arrival time (%f)"
                          " test results will be invalid!",
                          timestamp, ts)
            with self._results_lock:
                self.results.error("Clocks not synchronized")
                self.results.msgs_fail += 1
            self._output.write(', "error": "unsynchronized clocks"\n')
        else:
            with self._results_lock:
                self.results.start_time = (min(self.results.start_time, ts)
                                           if self.results.start_time else ts)
                self.results.stop_time = (max(self.results.stop_time, ts)
                                          if self.results.stop_time else ts)
                self.results.latency.update((ts - timestamp) * 1000)
                self.results.msgs_ok += 1
        self._output.write('}\n')

    def debug(self, ctx, publisher, event_type, payload, metadata):
        self._report("debug", ctx, publisher, event_type, payload, metadata)

    def audit(self, ctx, publisher, event_type, payload, metadata):
        self._report("audit", ctx, publisher, event_type, payload, metadata)

    def critical(self, ctx, publisher, event_type, payload, metadata):
        self._report("critical", ctx, publisher, event_type, payload, metadata)

    def error(self, ctx, publisher, event_type, payload, metadata):
        self._report("error", ctx, publisher, event_type, payload, metadata)

    def info(self, ctx, publisher, event_type, payload, metadata):
        self._report("info", ctx, publisher, event_type, payload, metadata)

    def warn(self, ctx, publisher, event_type, payload, metadata):
        self._report("warn", ctx, publisher, event_type, payload, metadata)


class Controller(_Base):
    """The test controller
    """
    def __init__(self, cfg, ctl_url, topic, timeout, unique=False, idle=2,
                 output=None):
        # each controller has a unique topic not to be confused
        # with future or past controller instances
        self.topic = topic
        self._idle = idle
        self.unique = unique
        super(Controller, self).__init__(cfg, ctl_url, topic, output,
                                         unique=False,
                                         name=None,
                                         kind=None,
                                         timeout=timeout)
        self._total_minions = 0
        self._queue = queue.Queue()

        # count of clients per type
        self._minions = dict([(k, 0) for k in MESSAGING_CLIENT_TYPES])
        # aggregated client results per type
        self._results = dict([(k, TestResults())
                              for k in MESSAGING_CLIENT_TYPES])
        # control rpc client for each type:
        self._clients = dict()

    def start(self):
        super(Controller, self).start()
        logging.debug("Polling for clients...")
        reply = {'exchange': self.ctl_target.exchange,
                 'topic': self.ctl_target.topic,
                 'server': self.ctl_target.server}
        for kind in MESSAGING_CLIENT_TYPES:
            target = om.Target(exchange=CONTROL_EXCHANGE,
                               topic=CLIENT_TOPIC %
                               ((kind, self.topic)
                                if not self.unique else (kind, 'singleton')),
                               fanout=True)
            self._clients[kind] = om.RPCClient(self.ctl_tport, target=target)
            self._clients[kind].cast({}, 'client_ping', reply_addr=reply)

        # wait until no more clients reply to the ping
        # (things are idle)
        _wait_stabilize(self._idle, lambda: self._total_minions)

    def shutdown(self):
        """Shutdown this Controller
        """
        super(Controller, self).shutdown({})
        self.wait()

    def shutdown_clients(self):
        """Shutdown all clients listening to $topic
        """
        for kind in MESSAGING_CLIENT_TYPES:
            self._clients[kind].cast({}, 'shutdown')
        time.sleep(1.0)

    def run_call_test(self, count, data, verbose, pause):
        clients = self._minions[RPC_CLIENT]
        servers = self._minions[RPC_SERVER]
        kwargs = {'verbose': verbose,
                  'pause': pause,
                  'data': data,
                  'count': count}
        self._run_test(RPC_CLIENT, 'test_call', kwargs)
        # note: set the poll time to 2x the client's pause between calls,
        # otherwise we're polling too frequently
        self._query_servers(RPC_SERVER, pause * 2, count * clients)

        print("RPC call test results")
        print("%d RPC clients, %d RPC Servers (%d total)"
              % (clients, servers, clients + servers))

        print("\n")
        print("Aggregated RPC Client results:")
        print("------------------------------")
        self._results[RPC_CLIENT].print_results()
        print("\n")
        print("Aggregated RPC Server results:")
        print("------------------------------")
        self._results[RPC_SERVER].print_results()

    def run_cast_test(self, count, data, verbose, pause, delay):
        clients = self._minions[RPC_CLIENT]
        servers = self._minions[RPC_SERVER]
        kwargs = {'verbose': verbose,
                  'pause': pause,
                  'data': data,
                  'count': count}
        self._run_test(RPC_CLIENT, 'test_cast', kwargs)
        # cast are async, wait a bit for msgs to propagate
        time.sleep(delay)
        # note: set the poll time to 2x the client's pause between calls,
        # otherwise we're polling too frequently
        self._query_servers(RPC_SERVER, pause * 2, count * clients)

        print("RPC cast test results")
        print("%d RPC clients, %d RPC Servers (%d total)"
              % (clients, servers, clients + servers))

        print("\n")
        print("Aggregated RPC Client results:")
        print("------------------------------")
        self._results[RPC_CLIENT].print_results()
        print("\n")
        print("Aggregated RPC Server results:")
        print("------------------------------")
        self._results[RPC_SERVER].print_results()

    def run_fanout_test(self, count, data, verbose, pause,
                        delay):
        clients = self._minions[RPC_CLIENT]
        servers = self._minions[RPC_SERVER]
        kwargs = {'verbose': verbose,
                  'pause': pause,
                  'data': data,
                  'count': count}
        self._run_test(RPC_CLIENT, 'test_fanout', kwargs)
        # fanouts are async, wait a bit for msgs to propagate
        time.sleep(delay)
        # note: set the poll time to 2x the client's pause between calls,
        # otherwise we're polling too frequently
        self._query_servers(RPC_SERVER, pause * 2,
                            count * clients * servers)

        print("RPC fanout test results")
        print("%d RPC clients, %d RPC Servers (%d total)"
              % (clients, servers, clients + servers))

        print("\n")
        print("Aggregated RPC Client results:")
        print("------------------------------")
        self._results[RPC_CLIENT].print_results()
        print("\n")
        print("Aggregated RPC Server results:")
        print("------------------------------")
        self._results[RPC_SERVER].print_results()

        start = self._results[RPC_CLIENT].start_time
        stop = self._results[RPC_SERVER].stop_time
        print("\n")
        print("Fanout propagation delay:")
        print("-------------------------")
        print("  First client transmit time: %f" % start)
        print("  Last server receive time: %f" % stop)
        print("  Duration (secs): %f" % (stop - start))

    def run_notification_test(self, count, data, severity, verbose, pause,
                              delay):
        clients = self._minions[NOTIFIER]
        servers = self._minions[LISTENER]
        kwargs = {'verbose': verbose,
                  'pause': pause,
                  'data': data,
                  'count': count,
                  'severity': severity}
        self._run_test(NOTIFIER, 'test_notify', kwargs)
        # notifications are async, wait a bit for msgs to propagate
        time.sleep(delay)
        # note: set the poll time to 2x the client's pause between calls,
        # otherwise we're polling too frequently
        self._query_servers(LISTENER, pause * 2, count * clients)

        print("Notification test results")
        print("%d Notifiers, %d Listeners (%d total)"
              % (clients, servers, clients + servers))

        print("\n")
        print("Aggregated Notifier (Client) results:")
        print("------------------------------------")
        self._results[NOTIFIER].print_results()
        print("\n")
        print("Aggregated Listener (Server) results:")
        print("-------------------------------------")
        self._results[LISTENER].print_results()

    def _run_test(self, kind, test, kwargs):
        """Tell the messaging clients to run a test.  When the client completes
        it will call the 'client_result' method below.
        """
        count = self._minions[kind]
        if count == 0:
            raise Exception("No %s clients visible" % kind)

        reply = {'exchange': self.ctl_target.exchange,
                 'topic': self.ctl_target.topic,
                 'server': self.ctl_target.server}

        # tell 'kind' clients to run the test
        self._clients[kind].cast({}, 'run_test',
                                 test=test,
                                 kwargs=kwargs,
                                 reply_addr=reply)

        results_per_client = dict()
        # wait for the clients to send results
        while count:
            try:
                name, ckind, results = self._queue.get(timeout=self._timeout)
            except queue.Empty:
                raise Exception("%s test timed out: no response from clients!"
                                % test)
            results_per_client[name] = results.to_dict()
            self._results[ckind].merge(results)
            if ckind == kind:
                count -= 1
            else:
                # TODO(kgiusti) uh, is this a problem?
                logging.warning("Huh? results from %s while expecting a %s",
                                ckind, kind)
        self._output.write(json.dumps(results_per_client) + '\n')

    def _query_servers(self, kind, pause, total):
        """Ask the servers for any data gathered during the test. The servers
        will respond by calling the 'client_result' method below.  Once the
        servers stop reporting new statistics the query is done.

        :param kind: the type of server to query - RPC or LISTENER
        :type kind: str
        :param pause: time in seconds to wait between each server poll.  Should
                      be at least twice the client's inter-message pause time.
        :type pause: float
        :param total: total number of messages expected to be received by all
                      servers
        """
        if self._minions[kind] == 0:
            raise Exception("No %s servers visible" % kind)

        # avoid hammering the servers if no pause given
        pause = max(pause, 0.250) if pause else 0.250

        server_results = self._results[kind]
        reply = {'exchange': self.ctl_target.exchange,
                 'topic': self.ctl_target.topic,
                 'server': self.ctl_target.server}

        logging.debug("Querying servers...")

        results_per_server = dict()
        done = False
        start = now()
        while not done and abs(now() - start) < self._timeout:

            # tell 'kind' servers to return results
            self._clients[kind].cast({}, 'get_server_results',
                                     reply_addr=reply)
            # wait for the servers to send results
            count = self._minions[kind]
            seen = 0
            while count:
                try:
                    _ = self._queue.get(timeout=self._timeout)
                    name, ckind, results = _
                except queue.Empty:
                    raise Exception("%s test timed out: no response from"
                                    " servers!" % kind)

                if ckind != kind:
                    # TODO(kgiusti): uh, is this a problem?
                    logging.warning("Huh? results from %s while expecting %s",
                                    ckind, kind)
                    continue
                if name not in results_per_server:
                    results_per_server[name] = results
                else:
                    results_per_server[name].merge(results)

                server_results.merge(results)
                seen += results.msgs_ok + results.msgs_fail
                count -= 1

            # exit loop once the expected number of messages have been received
            # by the servers, or the test times out
            done = server_results.msgs_ok + server_results.msgs_fail >= total
            if not done:
                time.sleep(pause)
                if seen == 0:
                    # no replies: try pausing longer next time
                    pause = min(pause * 2.0, self._timeout)

        if not done:
            logging.error("Test timed out - not all messages accounted for")
        results_per_server = dict([[k, v.to_dict()]
                                   for k, v in results_per_server.items()])
        self._output.write(json.dumps(results_per_server) + '\n')

        logging.debug("... servers queried")

    #
    # RPC calls:
    #
    def client_pong(self, ctxt, kind, name):
        # A client 'name' is checking in
        if kind not in self._minions:
            self._minions[kind] = 0
        self._minions[kind] += 1
        self._total_minions += 1
        logging.debug("New %s detected (%s) - %d total clients found",
                      kind, name, self._total_minions)
        return True

    def client_result(self, ctxt, name, kind, results):
        # A test client is reporting a test result in response to the above
        # _run_test method.
        logging.debug("%s results received from %s", (kind, name))
        try:
            self._queue.put((name, kind, TestResults.from_dict(results)))
        except Exception as exc:
            logging.error("Invalid TestResult from %s:%s (%s)",
                          kind, str(exc), str(results))
