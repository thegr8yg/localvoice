from localvoice.ptt import Action, PushToTalk, State, VK_ESCAPE


def test_hold_and_release_transcribes():
    p = PushToTalk()
    assert p.press(0.0) == [Action.START]
    assert p.release(1.5) == [Action.STOP]
    assert p.state is State.IDLE


def test_single_short_tap_is_discarded():
    p = PushToTalk()
    p.press(0.0)
    assert p.release(0.1) == [Action.CANCEL]


def test_double_tap_locks_then_press_finishes():
    p = PushToTalk()
    p.press(0.0)
    p.release(0.1)
    assert p.press(0.25) == [Action.START]
    assert p.release(0.35) == []
    assert p.state is State.LOCKED
    assert p.other_key(0x41) == []  # typing other keys doesn't stop hands-free mode
    assert p.press(5.0) == [Action.STOP]
    assert p.release(5.1) == []  # the release of the finishing press is ignored
    assert p.state is State.IDLE


def test_slow_taps_do_not_lock():
    p = PushToTalk()
    p.press(0.0)
    p.release(0.1)
    p.press(2.0)
    assert p.release(2.1) == [Action.CANCEL]


def test_double_tap_disabled_short_press_still_transcribes():
    p = PushToTalk(double_tap_lock=False)
    p.press(0.0)
    assert p.release(0.1) == [Action.STOP]


def test_other_key_while_holding_cancels():
    p = PushToTalk()
    p.press(0.0)
    assert p.other_key(0x43) == [Action.CANCEL]
    assert p.release(1.0) == []
    assert p.press(2.0) == [Action.START]


def test_escape_cancels_hands_free():
    p = PushToTalk()
    p.press(0.0); p.release(0.1); p.press(0.2); p.release(0.3)
    assert p.other_key(VK_ESCAPE) == [Action.CANCEL]
    assert p.state is State.IDLE
