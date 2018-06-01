ombt
====

A simple Oslo Messaging Benchmarking Tool (ombt) which can be used to
measure the latency and throughput of RPC and Notification
transactions.  This tool has been designed expressly for generating
and measuring messaging traffic in a distributed fashion.

The intent is to have a tool that can be used in different distributed
configurations to get some basic insights into scalability under load.

There are two tools provided: the original 'ombt' tool which was
limited to RPC testing, and the new 'ombt2' tool which adds
notification testing and better control of the test clients.

It is recommended to use 'ombt2' - 'ombt' is provided for legacy
reasons.

Prerequisites
-------------

ombt(2) has dependencies on other python packages.  These packages are
listed in the 'requirements.txt' file.  To install these packages, use
pip with the '-r' option:

 pip install -r ./requirements.txt

or use the 'extras' syntax:

 pip install .[amqp1]      # install from repo
 pip install ombt[amqp1]   # install from PyPi


ombt
----

This is the legacy ombt RPC-only tool. It is recommended to use the
newer ombt2 tool instead (see below).  This section is provided for
posterity.

A simple standalone test with single client and single server:

  ombt.py --calls 1000 --url rabbit://127.0.0.1:5672

Which will start a server, create a client and make 1000 RPC calls and
report the average latency for each call and the throughput achieved.

A more realistic test will usually involve starting multiple
processes, e.g. start N processes (on any number of machines, provided
they all point at the correct messaging broker) with

  ombt.py --url rabbit://127.0.0.1:5672

each of which will start a server in the RPC group, then run

  ombt.py --calls 1000 --controller --url rabbit://127.0.0.1:5672

which will tell all the servers to create a client and make 1000 calls
on the RPC server group, then report back the details. The controller
process will then collate all the results from each process and print
a summary of latency and throughput.

To use a different driver you can alter the url scheme:

  ombt.py --url amqp://127.0.0.1:5672

ombt2
-----

Next generation ombt test that provides fully distributed traffic for
both RPC calls and Notifications.

With ombt2 you can:

1. run either a standalone RPC test (just like old ombt) or standalone Notification test
2. deploy dedicated test servers (both RPC or Notification listeners)
3. deploy dedicated test clients (both RPC or Notification notifiers)
4. orchestrate load tests across the servers and clients


ombt2 uses 'subcommands' to run in different operational
modes. Supported modes are:

 * rpc - standalone loopback RPC test similar to the old ombt.py test
 * notify - standalone loopback Notification test
 * rpc-server - runs a single RPC Server process
 * rpc-client - runs a single RPC Client process
 * listener - runs a single Notification listener process
 * notifier - runs a single Notifier process
 * controller - orchestrates tests across the non-standalone clients
   and servers

To run a multi-client/server test, one would:

 1) set up one or more servers using rpc-server or listener mode
 2) set up one or more clients using rpc-client or notifier mode
 3) run a controller to submit a test and print the results

For example, to set up an RPC test using one RPC server and two RPC
clients using the AMQP 1.0 driver and run the RPC call test:

    $ ombt2 --url amqp://localhost:5672 rpc-server --daemon
    $ ombt2 --url amqp://localhost:5672 rpc-client --daemon
    $ ombt2 --url amqp://localhost:5672 rpc-client --daemon
    $ ombt2 --url amqp://localhost:5672 controller rpc-call calls=10
    Latency (millisecs):    min=2, max=5, avg=2.828724, std-dev=0.651274
    Throughput (calls/sec): min=345, max=358, avg=352.382622, std-dev=6.476285
     - Averaged 20 operations over 2 client(s)

The "--daemon" option causes the ombt2 command to run in the
background once the test client has completed initialization and is
ready to begin testing.  This option is recommended over simply
backgrounding the ombt2 command via job control (i.e. '&'), as it
avoids the possible race between client initialization and running the
controller.  With "--daemon" you know it is safe to start the test
once the ombt2 command has returned control of the terminal.

Note: controller commands (like rpc-call) can take arguments.  These
arguments must be specified in 'key=value' format:

 * rpc-call, rpc-cast:
   * length=N - the size of the payload in bytes (default 1024)
   * calls=N - number of calls/casts to execute (default 1)
   * pause=N - delay in milliseconds between each call/cast (default 0)
   * verbose - turn on extra logging (default off)

 * notify:
   * length=N - the size of the payload in bytes (default 1024)
   * calls=N - number of calls/casts to execute (default 1)
   * pause=N - delay in milliseconds between each call/cast (default 0)
   * verbose - turn on extra logging (default off)
   * severity=level - the severity level for the notifications, valid values:  debug (default), audit, critical, error, info, warn


You can re-run the controller command as many times as you wish using
the same test clients and servers.  Each run of the controller will
start a new test.  When done, you can use the controller to force all
servers and clients to shutdown:

    $ ./ombt2 --url amqp://localhost:5672 controller shutdown
    [2]   Done           ./ombt2 --url amqp://localhost:5672 rpc-server
    [3]-  Done           ./ombt2 --url amqp://localhost:5672 rpc-client
    [4]+  Done           ./ombt2 --url amqp://localhost:5672 rpc-client

You can also run servers and clients in groups where the traffic is
isolated to only those members of the given group. Use the --topic
argument to specify the group for the server/client. For example, here
are two separate groups of listeners/notifiers: 'groupA' and 'groupB':

    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupA' listener --daemon
    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupA' notifier --daemon
    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupB' listener --daemon
    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupB' listener --daemon
    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupB' notifier --daemon
    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupB' notifier --daemon
    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupB' notifier --daemon
    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupA' controller notify calls=10
    Latency (millisecs):    min=0, max=2, avg=1.251027, std-dev=0.517035
    Throughput (calls/sec): min=790, max=790, avg=790.019900, std-dev=0.000000
     - Averaged over 1 client(s)

    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupB' controller notify calls=10
    Latency (millisecs):    min=1, max=2, avg=1.225633, std-dev=0.256935
    Throughput (calls/sec): min=783, max=843, avg=807.523300, std-dev=25.903798
     - Averaged over 3 client(s)

    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupA' controller shutdown
    [2]   Done          ./ombt2 --url amqp://localhost:5672 --topic 'groupA' listener --daemon
    [5]   Done          ./ombt2 --url amqp://localhost:5672 --topic 'groupA' notifier --daemon
    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupB' controller shutdown
    [3]   Done          ./ombt2 --url amqp://localhost:5672 --topic 'groupB' listener --daemon
    [4]   Done          ./ombt2 --url amqp://localhost:5672 --topic 'groupB' listener --daemon
    [6]   Done          ./ombt2 --url amqp://localhost:5672 --topic 'groupB' notifier --daemon
    [7]-  Done          ./ombt2 --url amqp://localhost:5672 --topic 'groupB' notifier --daemon
    [8]+  Done          ./ombt2 --url amqp://localhost:5672 --topic 'groupB' notifier --daemon


The ombt2 tool uses the message bus not only for test traffic
but also for control of the servers and clients.  The controller
command uses RPC to orchestrate the test, invoking methods on the
servers and clients to do so.

In some cases this is undesireable, for example when load testing the
message bus or during fault recovery testing.  If the message bus
becomes unstable it will effect the proper operation of the test due
to ombt2 reliance on the bus's operation.

For these reasons ombt2 allows you to use a second message bus as the
control bus.  No test traffic flows across this control bus nor does
any control traffic flow over the message bus under test.

Use the ombt2 command option --control to specify the URL address of
the message bus to use as the control bus.  The address of the message
bus under test is determined by the --url command option.  For
example:

    $ ./ombt2 --url amqp://localhost:5672 --control amqp://otherhost:5672 rpc-server &
    $ ./ombt2 --url amqp://localhost:5672 --control amqp://otherhost:5672 rpc-client &

uses two separate message buses: 'localhost' as the message bus under
test and 'otherhost' for control traffic.  Since the controller
command never sends or receives test traffic you only need to specify
the --control URL for that command.  For backward compatibility the
value of the --url option is used for both command and test traffic if
the --control option is not present.

Docker Notes
============

Build the docker image

    docker build . -t myombt:latest

Using the previously built image (e.g with rabbit)

    docker run -d --hostname my-rabbit --name myrabbit rabbitmq:3
    docker run --link myrabbit:myrabbit -d -ti myombt --debug  --url rabbit://myrabbit:5672 rpc-server
    docker run --link myrabbit:myrabbit -d -ti myombt --debug  --url rabbit://myrabbit:5672 rpc-client
    docker run --link myrabbit:myrabbit  -ti myombt --debug  --url rabbit://myrabbit:5672 controller rpc-call --calls 10
    docker run --link myrabbit:myrabbit  -ti myombt --debug  --url rabbit://myrabbit:5672 controller shutdown

-------------------------------------------------------------------------------

Message Bus Configuration Notes
===============================

These notes may be out of date.  You'd be better off consulting the
Oslo.Messaging [documentation][omdocs] upstream for the most up to
date deployment guides.

[omdocs]: https://docs.openstack.org/developer/oslo.messaging "Oslo Messaging Documentation"

Qpid C++ broker
---------------

Setting up qpidd to work with the AMQP 1.0 driver requires qpid 0.26
or later, with 1.0 support enabled and appropriate queue and topic
patterns specified, e.g.

  ./src/qpidd --load-module=./src/amqp.so --auth no --queue-patterns exclusive --queue-patterns unicast --topic-patterns broadcast

Qpid Dispatch Router
--------------------

Setting up Qpid Dispatch Router to work with the AMQP 1.0 driver
requires version 0.6.1 or later of the router.  To configure the
router you must add the following address definitions to your
__qdrouterd__ configuration file (located by default in
/etc/qpid-dispatch/qdrouterd.conf):


    address {
      prefix: openstack.org/om/rpc/multicast
      distribution: multicast
    }

    address {
      prefix: openstack.org/om/rpc/unicast
      distribution: closest
    }

    address {
      prefix: openstack.org/om/rpc/anycast
      distribution: balanced
    }

    address {
      prefix: openstack.org/om/notify/multicast
      distribution: multicast
    }

    address {
      prefix: openstack.org/om/notify/unicast
      distribution: closest
    }

    address {
      prefix: openstack.org/om/notify/anycast
      distribution: balanced
    }

--------






