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

import os
from setuptools import setup

_VERSION = "3.0.0"   # NOTE: update ombt/_main.py too!

_dependencies = ["oslo.messaging"]


setup(name="ombt",
      version=_VERSION + os.environ.get('OMBT_VERSION_SUFFIX', ''),
      author="Ken Giusti",
      author_email="kgiusti@gmail.com",
      description="Oslo.Messaging Benchmark Tool",
      url="https://github.com/kgiusti/ombt",
      packages=["ombt"],
      license="Apache Software License",
      install_requires=_dependencies,
      entry_points={
          'console_scripts': [
              'ombt = ombt._main:main',
              'ombt2 = ombt._main:main',
          ],
      },
      extras_require={
          'amqp1': ['pyngus'],
          'kafka': ['kafka-python>=1.3.1', 'tenacity>=4.4.0']
      },
      classifiers=["License :: OSI Approved :: Apache Software License",
                   "Intended Audience :: Developers",
                   "Operating System :: OS Independent",
                   "Programming Language :: Python",
                   "Programming Language :: Python :: 2",
                   "Programming Language :: Python :: 2.7",
                   "Programming Language :: Python :: 3",
                   "Programming Language :: Python :: 3.3",
                   "Programming Language :: Python :: 3.4",
                   "Programming Language :: Python :: 3.5",
                   "Programming Language :: Python :: 3.6"])
