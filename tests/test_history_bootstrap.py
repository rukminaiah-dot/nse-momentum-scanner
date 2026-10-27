from unittest.mock import Mock
from v2.backend.history_bootstrap import main


def test_database_failure_does_not_abort_live_scanner_startup(capsys):
    broken = Mock(side_effect=ConnectionError('secret'))
    active = Mock()
    main((broken, active))
    active.assert_called_once()
    output=capsys.readouterr().out
    assert 'HISTORY_BACKUP_UNAVAILABLE' in output
    assert 'secret' not in output
