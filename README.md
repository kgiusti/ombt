ombt
====

A simple oslo messaging benchmarking tool, currently allowing the latency and throughput of RPC calls to be measured.

The intent is to have a tool that can be used in different configurations to get some basic insights into scalability. At present it focuses on RPC calls on a topic to which one or more servers are subscribed.

A simple standalone test with single client and single server:

  obmt.py --calls 1000 --conf transport_url amqp://127.0.0.1:5672
  
Which will start a server, create a client and make 1000 RPC calls and report the average latency for each call and the throughput achieved.

A more realistic test will usually involve starting multiple processes, e.g. start N processes (on any number of machines, provided they all point at the correct messaging broker) with

  ombt.py --conf transport_url amqp://127.0.0.1:5672
  
each of which will start a server in the RPC group, then run

  ombt.py --calls 1000 --controller --conf transport_url amqp://127.0.0.1:5672

which will tell all the servers to create a client and make 1000 calls on the RPC server group, then report back the details. The controller process will then collate all the results from each process and print a summary of latency and throughput.

To use a different driver you can either alter the transport url or use other configuration options, e.g.

  ombt.py --conf rpc_backend rabbit --conf rabbit_host 127.0.0.1:5672
  
--------------------------------------------------------------------------------------------------------------------------

Setting up qpidd to work with the AMQP 1.0 driver requires qpid 0.26 or later, with 1.0 support enabled and appropriate queue and topic patterns specified, e.g.

  ./src/qpidd --load-module=./src/amqp.so --auth no --queue-patterns exclusive --queue-patterns unicast --topic-patterns broadcast
  
Setting up Qpid Dispatch Router to work with the same driver requires 0.2[1] or later and adding the following address definitions to your config file(s):

fixed-address {
    prefix: /unicast
    fanout: single
    bias: closest
}

fixed-address {
    prefix: /exclusive
    fanout: single
    bias: closest
}

fixed-address {
    prefix: /broadcast
    fanout: multiple
}

[1] You will also probably want the patch attached to https://issues.apache.org/jira/browse/DISPATCH-51 if using 0.2
