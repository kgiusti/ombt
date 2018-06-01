FROM ubuntu:16.04

RUN apt update && \
  apt install -y gcc python-dev python-pip &&\
  pip install --upgrade pip


RUN  useradd -u 64400 -m ombt

COPY . /home/ombt/source

WORKDIR /home/ombt/source

RUN pip install .[amqp1]

USER ombt
ENV HOME /home/ombt
WORKDIR /home/ombt/source

ENTRYPOINT ["ombt"]
