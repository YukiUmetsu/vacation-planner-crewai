from db import keys


def test_user_pk() -> None:
    assert keys.user_pk("abc") == "USER#abc"


def test_trip_sk() -> None:
    assert keys.trip_sk("t1") == "TRIP#t1"


def test_route_sk() -> None:
    assert keys.route_sk("t1") == "TRIP#t1#ROUTE"


def test_day_sk_zero_padded() -> None:
    assert keys.day_sk("t1", 1) == "TRIP#t1#DAY#01"
    assert keys.day_sk("t1", 12) == "TRIP#t1#DAY#12"


def test_gsi1_keys() -> None:
    assert keys.gsi1_pk("t1") == "TRIP#t1"
    assert keys.gsi1_sk_user("abc") == "USER#abc"
    assert keys.gsi1_sk_route() == "ROUTE"
    assert keys.gsi1_sk_day(3) == "DAY#03"
