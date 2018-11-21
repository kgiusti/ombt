ombt
====

A simple Oslo Messaging Benchmarking Tool (ombt) which can be used to
measure the latency and throughput of RPC and Notification
transactions.  This tool has been designed expressly for generating
and measuring messaging traffic in a distributed fashion.

The intent is to have a tool that can be used in different distributed
configurations to get some basic insights into scalability under load.


Prerequisites
-------------

ombt has dependencies on other python packages.  These packages are
listed in the 'requirements.txt' file.  To install these packages, use
pip with the '-r' option:

 pip install -r ./requirements.txt

or use the 'extras' syntax:

 pip install .[amqp1]      # install from repo
 pip install ombt[amqp1]   # install from PyPi


ombt
----

With ombt you can:

1. run either a standalone test for RPC or Notifications
2. deploy dedicated test servers (both RPC or Notification listeners)
3. deploy dedicated test clients (both RPC or Notification notifiers)
4. orchestrate load tests across the servers and clients


ombt uses 'subcommands' to run in different operational
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

For example let us set up an RPC call test using one RPC server and
two RPC clients using the AMQP 1.0 driver and run the RPC call test.
This example assumes you are running the RabbitMQ broker on the local
host:

    $ ombt rpc-server --daemon
    $ ombt rpc-client --daemon
    $ ombt rpc-client --daemon
    $ ombt controller rpc-call --calls=10

The test will run and print out the results.  For example:

    RPC call test results
    2 RPC clients, 1 RPC Servers (3 total)


    Aggregated RPC Client results:
    ------------------------------
    Total Messages: 20
    Test Interval: 1542827906.192293 - 1542827906.228337 (0.036044 secs)
    Aggregate throughput: 554.875513 msgs/sec
    Latency 20 samples (msecs): Average 3.454173 StdDev 0.346421 Min 3.052950 Max 4.543066
    Latency Distribution: 
    [0..<1):  0
    [1..<2):  0
    [2..<3):  0
    [3..<4):  19
    [4..<5):  1
    [5..<6):  0
    [6..<7):  0
    [7..<8):  0
    [8..<9):  0
    [9..<10):  0


    Aggregated RPC Server results:
    ------------------------------
    Total Messages: 20
    Test Interval: 1542827906.194713 - 1542827906.227007 (0.032294 secs)
    Aggregate throughput: 619.313990 msgs/sec
    Latency 20 samples (msecs): Average 2.264357 StdDev 0.316320 Min 1.920938 Max 3.316164
    Latency Distribution: 
    [0..<1):  0
    [1..<2):  3
    [2..<3):  16
    [3..<4):  1
    [4..<5):  0
    [5..<6):  0
    [6..<7):  0
    [7..<8):  0
    [8..<9):  0
    [9..<10):  0


The "--daemon" option causes the ombt command to run in the
background once the test client has completed initialization and is
ready to begin testing.  This option is recommended over simply
backgrounding the ombt command via job control (i.e. '&'), as it
avoids the possible race between client initialization and running the
controller.  With "--daemon" you know it is safe to start the test
once the ombt command has returned control of the terminal.

By default ombt expects the RabbitMQ broker to be running on the local
host.  You can override that by using the --url option:

  $ ombt --url rabbit://somehost.com:5672 ...

Note: ombt commands (like rpc-call) can take arguments.  These
arguments must be specified in '--key=value' format.  Use '--help' at
any point for a description of the supported arguments:

  $ ombt controller rpc-call --help
  usage: ombt controller rpc-call [-h] [--length LENGTH] [--calls CALLS] [--pause PAUSE]

  run RPC call test

  optional arguments:
    -h, --help       show this help message and exit
    --length LENGTH  payload size in bytes
    --calls CALLS    number of calls to make
    --pause PAUSE    Limit the rate of RPC calls by pausing FLOAT seconds between issuing each call


You can re-run the controller command as many times as you wish using
the same test clients and servers.  Each run of the controller will
start a new test.  When done, you can use the controller to force all
servers and clients to shutdown:

    $ ombt controller shutdown

You can also run servers and clients in groups where the traffic is
isolated to only those members of the given group. Use the --topic
argument to specify the group for the server/client. For example, here
are two separate groups of listeners/notifiers: 'groupA' and 'groupB':

    $ ombt --topic 'groupA' listener --daemon
    $ ombt --topic 'groupA' notifier --daemon
    $ ombt --topic 'groupB' listener --daemon
    $ ombt --topic 'groupB' listener --daemon
    $ ombt --topic 'groupB' notifier --daemon
    $ ombt --topic 'groupB' notifier --daemon
    $ ombt --topic 'groupB' notifier --daemon

    $ ombt --topic 'groupA' controller notify --events=10
    Notification test results
    1 Notifiers, 1 Listeners (2 total)


    Aggregated Notifier (Client) results:
    ------------------------------------
    Total Messages: 10
    Test Interval: 1542828591.948388 - 1542828591.971192 (0.022804 secs)
    Aggregate throughput: 438.523723 msgs/sec
    Latency 10 samples (msecs): Average 2.260280 StdDev 3.954730 Min 0.823021 Max 14.119864
    Latency Distribution: 
    [0..<1):  7
    [1..<2):  2
    [2..<3):  0
    [3..<4):  0
    [4..<5):  0
    [5..<6):  0
    [6..<7):  0
    [7..<8):  0
    [8..<9):  0
    [9..<10):  0
    [10..<20):  1
    [20..<30):  0
    [30..<40):  0
    [40..<50):  0
    [50..<60):  0
    [60..<70):  0
    [70..<80):  0
    [80..<90):  0
    [90..<100):  0


    Aggregated Listener (Server) results:
    -------------------------------------
    Total Messages: 10
    Test Interval: 1542828591.963562 - 1542828591.973547 (0.009985 secs)
    Aggregate throughput: 1001.505253 msgs/sec
    Latency 10 samples (msecs): Average 4.353619 StdDev 3.612418 Min 2.789974 Max 15.172958
    Latency Distribution: 
    [0..<1):  0
    [1..<2):  0
    [2..<3):  3
    [3..<4):  6
    [4..<5):  0
    [5..<6):  0
    [6..<7):  0
    [7..<8):  0
    [8..<9):  0
    [9..<10):  0
    [10..<20):  1
    [20..<30):  0
    [30..<40):  0
    [40..<50):  0
    [50..<60):  0
    [60..<70):  0
    [70..<80):  0
    [80..<90):  0
    [90..<100):  0

    $ ombt --topic 'groupB' controller notify --events=10
    Notification test results
    3 Notifiers, 3 Listeners (6 total)


    Aggregated Notifier (Client) results:
    ------------------------------------
    Total Messages: 30
    Test Interval: 1542830818.586133 - 1542830818.615070 (0.028937 secs)
    Aggregate throughput: 1036.731344 msgs/sec
    Latency 30 samples (msecs): Average 2.606336 StdDev 4.197207 Min 1.063108 Max 17.767906
    Latency Distribution: 
    [0..<1):  0
    [1..<2):  27
    [2..<3):  0
    [3..<4):  0
    [4..<5):  0
    [5..<6):  0
    [6..<7):  0
    [7..<8):  0
    [8..<9):  0
    [9..<10):  0
    [10..<20):  3
    [20..<30):  0
    [30..<40):  0
    [40..<50):  0
    [50..<60):  0
    [60..<70):  0
    [70..<80):  0
    [80..<90):  0
    [90..<100):  0


    Aggregated Listener (Server) results:
    -------------------------------------
    Total Messages: 30
    Test Interval: 1542830818.601133 - 1542830818.617102 (0.015969 secs)
    Aggregate throughput: 1878.663442 msgs/sec
    Latency 30 samples (msecs): Average 5.304170 StdDev 3.752257 Min 2.674103 Max 18.431902
    Latency Distribution: 
    [0..<1):  0
    [1..<2):  0
    [2..<3):  2
    [3..<4):  11
    [4..<5):  9
    [5..<6):  5
    [6..<7):  0
    [7..<8):  0
    [8..<9):  0
    [9..<10):  0
    [10..<20):  3
    [20..<30):  0
    [30..<40):  0
    [40..<50):  0
    [50..<60):  0
    [60..<70):  0
    [70..<80):  0
    [80..<90):  0
    [90..<100):  0

    $ ombt --topic 'groupA' controller shutdown
    $ ombt --topic 'groupB' controller shutdown


The ombt tool uses the message bus not only for test traffic
but also for control of the servers and clients.  The controller
command uses RPC to orchestrate the test, invoking methods on the
servers and clients to do so.

In some cases this is undesireable, for example when load testing the
message bus or during fault recovery testing.  If the message bus
becomes unstable it will effect the proper operation of the test due
to ombt reliance on the bus's operation.

For these reasons ombt allows you to use a second message bus as the
control bus.  No test traffic flows across this control bus nor does
any control traffic flow over the message bus under test.

Use the ombt command option --control to specify the URL address of
the message bus to use as the control bus.  The address of the message
bus under test is determined by the --url command option.  For
example:

    $ ombt --url rabbit://localhost:5672 --control amqp://otherhost:5672 rpc-server --daemon
    $ ombt --url rabbit://localhost:5672 --control amqp://otherhost:5672 rpc-client --daemon

uses two separate message buses: 'localhost' as the message bus under
test and 'otherhost' for control traffic.  Since the controller
command never sends or receives test traffic you only need to specify
the --control URL for that command.  By default the value of the --url
option is used for both command and test traffic if the --control
option is not present.

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






