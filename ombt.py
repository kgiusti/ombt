#!/usr/bin/env python

import logging
import math
import optparse
import os
import signal
import socket
import sys
import threading
import time

from oslo.config import cfg
from oslo import messaging


class Stats(object):
    def __init__(self):
        self.min = None
        self.max = None
        self.total = 0
        self.count = 0
        self.average = None
        self.std_deviation = None
        self._sum_of_squares = 0

    def update(self, value):
        self._update(value)

    def merge(self, stats):
        self._update(stats.total, min_value=stats.min, max_value=stats.max, count=stats.count, squared=stats._sum_of_squares)

    def _update(self, value, min_value=None, max_value=None, count=1, squared=None):
        min_value = min_value or value
        max_value = max_value or value
        squared = squared or (value**2)

        if not self.min or min_value < self.min:
            self.min = min_value
        if not self.max or max_value > self.max:
            self.max = max_value
        self.total += value
        self.count += count
        self._sum_of_squares += squared
        n = float(self.count)
        self.average = self.total / n
        self.std_deviation = math.sqrt((self._sum_of_squares / n) - (self.average ** 2))

    def __str__(self):
        return "min=%i, max=%i, avg=%f, std-dev=%f" % (self.min, self.max, self.average, self.std_deviation)


class Test(object):
    def __init__(self):
        self.invocations = 0

    def reverse(self, ctx, value):
        self.invocations += 1
        if value:
            return value[::-1]
        else:
            raise ValueError("No input given")

    def get_invocation_count(self, ctx):
        return self.invocations


class Control(object):
    def __init__(self, transport, target, name):
        self._transport = transport
        self._target = target
        self.name = name
        self._client = None
        self._thread = None
        self._count = None
        self._data = None
        self._controller = None

    def start(self, ctx, controller, count=None, fanout=False, server=None, timeout=2, data="abcdefghijklmnopqrstuvwxyz"):
        if controller == self.name:
            return
        self._controller = controller
        target = self._target
        if fanout:
            target.fanout = True
        if server:
            target.server = server
        if count:
            self._count = count
        if data:
            self._data=data

        stub = messaging.RPCClient(self._transport, target, timeout=timeout)
        self._client = Client(stub)
        self._thread = threading.Thread(target=self.run)
        self._thread.start()

    def run(self):
        target = messaging.Target(exchange=self._target.exchange,
                                  topic=self._target.topic,
                                  server = self._controller)
        ctrlr = messaging.RPCClient(self._transport, target, timeout=5)

        ctrlr.cast({}, 'announce', server=self.name)
        stats = self._client.run(self._data, self._count)
        ctrlr.cast({}, 'submit', server=self.name, results=stats)


    def stop(self, ctx):
        if self._client:
            self._client.stop()
            self._client = None
        if self._thread:
            self._thread.join()
            self._thread = None


class Collector(object):
    def __init__(self):
        self.count = 0
        self._announced = 0
        self.workers = None
        self.throughput = Stats()
        self.latency = Stats()

    def expected(self):
        return self. workers if self.workers else self._announced

    def announce(self, ctxt, server):
        self._announced += 1

    def submit(self, ctxt, server, results):
        self.count += 1
        t = results['throughput']
        self.throughput.update(t)
        l = Stats()
        l.__dict__.update(results['latency'])
        self.latency.merge(l)
        print "    result %i of %i submitted by %s; Throughput: %i, Latency:%s" % (self.count, self.expected(), server, t, l)

    def report(self):
        print
        print "Latency (millisecs):    %s" % self.latency
        print "Throughput (calls/sec): %s" % self.throughput

    def is_complete(self):
        return self.expected() and self.expected() <= self.count

class Client(object):
    def __init__(self, client):
        self._stopped = False
        self._client = client

    def run(self, value, count=None, verbose=False):
        self.latency = Stats()
        self.calls = 0
        self.t0 = time.time()
        while not self._stopped:
            t = time.time()
            value = self._client.call({}, 'reverse', value=value)
            self.calls += 1
            if verbose and count and self.calls % (max(10, count)/10) == 0:
                print "Call %i of %i completed" % (self.calls, count)
            self.latency.update((time.time() - t) * 1000)
            if count and self.calls >= count:
                self._stopped = True
        return self.get_stats()

    def stop(self):
        self._stopped = True

    def get_stats(self):
        return {'latency':self.latency.__dict__,
                'throughput':self.calls/(time.time() - self.t0),
                'calls':self.calls}


class Server(object):
    def __init__(self, transport, name, controller, workers):
        target = messaging.Target(exchange="test-exchange",
                                  topic="test-topic",
                                  server=name)

        endpoints = [Test(), Control(transport, target, name)]
        if controller:
            self.collector = Collector()
            if workers:
                self.collector.workers = workers
            endpoints.append(self.collector)
        else:
            self.collector = None
        self._server = messaging.get_rpc_server(transport, target, endpoints)
        self._ctrl = messaging.RPCClient(transport, target, timeout=2)

    def start(self):
        self._thread = threading.Thread(target=self._server.start)
        self._thread.start()

    def stop(self, wait=False):
        self._server.stop()
        self._ctrl.cast({}, 'stop')
        if wait:
            self._server.wait()
            self.wait()

    def wait(self):
        if self.collector:
            while not self.collector.is_complete():
                time.sleep(0.5)
            self.stop()
        while self._thread.is_alive():
            time.sleep(0.5)
        #self._thread.join()


def handle_config_option(option, opt_string, opt_value, parser):
    name, value = opt_value
    setattr(cfg.CONF, name, value)


def main(argv=None):
    _usage = """Usage: %prog [options] <name>"""
    parser = optparse.OptionParser(usage=_usage)
    parser.add_option("--url", action="store", default=None)
    parser.add_option("--id", action="store", default=None)
    parser.add_option("--controller", action="store_true")
    parser.add_option("--calls", action="store", type=int, default=0)
    parser.add_option("--workers", action="store", type=int, default=None)
    parser.add_option("--timeout", action="store", type=int, default=2)
    parser.add_option("--config", action="callback",
                      callback=handle_config_option, nargs=2, type="string")

    opts, extra = parser.parse_args(args=argv)

    logging.basicConfig(level=logging.INFO)  #make this an option

    if opts.url:
        cfg.CONF.transport_url=opts.url

    transport = messaging.get_transport(cfg.CONF)

    server_name = opts.id or "%s_%s" % (socket.gethostname(), os.getpid())
    server = Server(transport, server_name, opts.controller, opts.workers)
    def signal_handler(s, f):
        server.stop()
    signal.signal(signal.SIGINT, signal_handler)

    server.start()
    if opts.controller:
        time.sleep(0.5) # give server time to initialise
        target = messaging.Target(exchange="test-exchange",
                                  topic="test-topic",fanout=True)
        stub = messaging.RPCClient(transport, target, timeout=2)
        stub.cast({}, 'start', controller=server_name, count=opts.calls,timeout=opts.timeout)
    elif opts.calls:
        target = messaging.Target(exchange="test-exchange",
                                  topic="test-topic")
        stub = messaging.RPCClient(transport, target, timeout=2)
        client = Client(stub)
        stats = client.run("abcdefghijklmnopqrstuvwxyz", count=opts.calls, verbose=True)
        print stats
        server.stop()
    server.wait()
    if opts.controller:
        server.collector.report()
    return 0

if __name__ == "__main__":
    sys.exit(main())
