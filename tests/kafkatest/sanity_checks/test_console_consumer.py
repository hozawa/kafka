# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ducktape.tests.test import Test
from ducktape.utils.util import wait_until
from ducktape.mark import parametrize
from ducktape.mark import matrix

from kafkatest.services.zookeeper import ZookeeperService
from kafkatest.services.kafka import KafkaService
from kafkatest.services.kafka.version import LATEST_0_8_2
from kafkatest.services.console_consumer import ConsoleConsumer
from kafkatest.utils.remote_account import line_count, file_exists
from kafkatest.services.verifiable_producer import VerifiableProducer
from kafkatest.utils.security_config import SecurityConfig


import time


class ConsoleConsumerTest(Test):
    """Sanity checks on console consumer service class."""
    def __init__(self, test_context):
        super(ConsoleConsumerTest, self).__init__(test_context)

        self.topic = "topic"
        self.zk = ZookeeperService(test_context, num_nodes=1)
        self.kafka = KafkaService(self.test_context, num_nodes=1, zk=self.zk,
                                  topics={self.topic: {"partitions": 1, "replication-factor": 1}})
        self.consumer = ConsoleConsumer(self.test_context, num_nodes=1, kafka=self.kafka, topic=self.topic)

    def setUp(self):
        self.zk.start()

    @parametrize(security_protocol=SecurityConfig.SSL, new_consumer=True)
    @matrix(security_protocol=[SecurityConfig.PLAINTEXT], new_consumer=[False, True])
    def test_lifecycle(self, security_protocol, new_consumer):
        """Check that console consumer starts/stops properly, and that we are capturing log output."""

        self.kafka.security_protocol = security_protocol
        self.kafka.start()

        self.consumer.security_protocol = security_protocol
        self.consumer.new_consumer = new_consumer

        t0 = time.time()
        self.consumer.start()
        node = self.consumer.nodes[0]

        wait_until(lambda: self.consumer.alive(node),
            timeout_sec=10, backoff_sec=.2, err_msg="Consumer was too slow to start")
        self.logger.info("consumer started in %s seconds " % str(time.time() - t0))

        # Verify that log output is happening
        wait_until(lambda: file_exists(node, ConsoleConsumer.LOG_FILE), timeout_sec=10,
                   err_msg="Timed out waiting for logging to start.")
        assert line_count(node, ConsoleConsumer.LOG_FILE) > 0

        # Verify no consumed messages
        assert line_count(node, ConsoleConsumer.STDOUT_CAPTURE) == 0

        self.consumer.stop_node(node)

    def test_version(self):
        """Check that console consumer v0.8.2.X successfully starts and consumes messages."""
        self.kafka.start()

        num_messages = 1000
        self.producer = VerifiableProducer(self.test_context, num_nodes=1, kafka=self.kafka, topic=self.topic,
                                           max_messages=num_messages, throughput=1000)
        self.producer.start()
        self.producer.wait()

        self.consumer.nodes[0].version = LATEST_0_8_2
        self.consumer.consumer_timeout_ms = 1000
        self.consumer.start()
        self.consumer.wait()

        num_consumed = len(self.consumer.messages_consumed[1])
        num_produced = self.producer.num_acked
        assert num_produced == num_consumed, "num_produced: %d, num_consumed: %d" % (num_produced, num_consumed)
