set -x

TOPICS="TOPIC111 TOPIC222 TOPIC333 TOPIC444 TOPIC555 TOPIC666 TOPIC777 TOPIC888"
for topic in $TOPICS; do
    COUNT=8
    for (( i=0 ; i<$COUNT ; ++i )); do
        ./ombt2 --url amqp://localhost:5672 --topic $topic listener --daemon
        ./ombt2 --url amqp://localhost:5672 --topic $topic notifier --daemon
        ./ombt2 --url amqp://localhost:5672 --topic $topic notifier --daemon
    done
done


function ping_em {
    for topic in $TOPICS; do
        ./ombt2 --url amqp://localhost:5672 --topic $topic controller notify --events 100 &
    done
}
export -f ping_em

function nuke_em {
    for topic in $TOPICS; do
        ./ombt2 --url amqp://localhost:5672 --topic $topic controller shutdown
    done
}
export -f nuke_em
set +x

