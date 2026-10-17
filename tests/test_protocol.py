import pytest

from edash.link import LineLink, ProtocolError
from edash.protocol import Hello, MailData, MailItem, MailMsg, TimeSync, decode, encode


def test_round_trip(now):
    message = MailMsg(data=MailData(unread_count=1, items=[MailItem(sender="A", subject="B", received=now)]))
    decoded = decode(encode(message))
    assert decoded == message


def test_unknown_fields_are_ignored():
    decoded = decode(b'{"type": "hello", "role": "host", "future_field": 1}')
    assert isinstance(decoded, Hello)


def test_link_numbers_messages_and_reassembles_chunks(fake_stream, now):
    sender = LineLink(fake_stream)
    sender.send(Hello(role="host"))
    sender.send(TimeSync(now=now))
    data = bytes(fake_stream.written)

    from tests.conftest import FakeStream

    receiver = LineLink(FakeStream([data[:7], data[7:30], data[30:]]))
    first, second = receiver.receive(), receiver.receive()
    assert (first.type, first.seq) == ("hello", 1)
    assert (second.type, second.seq, second.now) == ("time", 2, now)
    assert receiver.receive() is None  # read timeout


def test_junk_lines_raise_but_link_continues(fake_stream):
    fake_stream.feed(b"raspberrypi login: \n")
    fake_stream.feed(encode(Hello(role="device")))
    link = LineLink(fake_stream)
    with pytest.raises(ProtocolError):
        link.receive()
    assert isinstance(link.receive(), Hello)


def test_overlong_line_is_discarded(fake_stream):
    link = LineLink(fake_stream)
    link.MAX_LINE = 100
    fake_stream.feed(b"x" * 200)
    with pytest.raises(ProtocolError):
        link.receive()
