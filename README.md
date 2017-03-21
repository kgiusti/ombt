ombt
====

A simple oslo messaging benchmarking tool, currently allowing the
latency and throughput of RPC calls to be measured.

The intent is to have a tool that can be used in different
configurations to get some basic insights into scalability. At present
it focuses on RPC calls on a topic to which one or more servers are
subscribed.

Prerequisites
-------------

ombt[2] has dependencies on other python packages.  These packages are
listed in the 'requirements.txt' file.  To install these packages, use
pip with the '-r' option:

 pip install -r ./requirements.txt

Use
---
A simple standalone test with single client and single server:

  obmt.py --calls 1000 --url rabbit://127.0.0.1:5672

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

--------------------------------------------------------------------------------------------------------------------------

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

ombt2
=====

Next generation ombt test that provides fully distributed traffic for
both RPC calls and Notifications.

Refer to ombt above for message bus configuration instructions.

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

    $ ombt2 --url amqp://localhost:5672 rpc-server &
    $ ombt2 --url amqp://localhost:5672 rpc-client &
    $ ombt2 --url amqp://localhost:5672 rpc-client &
    $ ombt2 --url amqp://localhost:5672 controller rpc-call calls=10
    Latency (millisecs):    min=2, max=5, avg=2.828724, std-dev=0.651274
    Throughput (calls/sec): min=345, max=358, avg=352.382622, std-dev=6.476285
     - Averaged 20 operations over 2 client(s)

Note: controller commands (like rpc-call) can take arguments.  These
arguments must be specified in 'key=value' format.

You can use the controller to force all servers and clients to shutdown:

    $ ./ombt2 --url amqp://localhost:5672 controller shutdown
    [2]   Done                    ./ombt2 --url amqp://localhost:5672 rpc-server
    [3]-  Done                    ./ombt2 --url amqp://localhost:5672 rpc-client
    [4]+  Done                    ./ombt2 --url amqp://localhost:5672 rpc-client

You can also run servers in clients in groups where the traffic is
isolated to only those members of the given group. Use the --topic
argument to specify the group for the server/client. For example, here
are two separate groups of listeners/notifiers: 'groupA' and 'groupB':

    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupA' listener &
    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupA' notifier &
    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupB' listener &
    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupB' listener &
    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupB' notifier &
    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupB' notifier &
    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupB' notifier &
    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupA' controller notify calls=10
    Latency (millisecs):    min=0, max=2, avg=1.251027, std-dev=0.517035
    Throughput (calls/sec): min=790, max=790, avg=790.019900, std-dev=0.000000
     - Averaged over 1 client(s)

    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupB' controller notify calls=10
    Latency (millisecs):    min=1, max=2, avg=1.225633, std-dev=0.256935
    Throughput (calls/sec): min=783, max=843, avg=807.523300, std-dev=25.903798
     - Averaged over 3 client(s)

    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupA' controller shutdown
    [2]   Done                    ./ombt2 --url amqp://localhost:5672 --topic 'groupA' listener
    [5]   Done                    ./ombt2 --url amqp://localhost:5672 --topic 'groupA' notifier
    $ ./ombt2 --url amqp://localhost:5672 --topic 'groupB' controller shutdown
    [3]   Done                    ./ombt2 --url amqp://localhost:5672 --topic 'groupB' listener
    [4]   Done                    ./ombt2 --url amqp://localhost:5672 --topic 'groupB' listener
    [6]   Done                    ./ombt2 --url amqp://localhost:5672 --topic 'groupB' notifier
    [7]-  Done                    ./ombt2 --url amqp://localhost:5672 --topic 'groupB' notifier
    [8]+  Done                    ./ombt2 --url amqp://localhost:5672 --topic 'groupB' notifier





