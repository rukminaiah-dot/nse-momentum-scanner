"""History backup outages must not prevent read-only live market scanning."""
def main(initializers=None):
    if initializers is None:
        from .postgres_history import init_history, init_active_trade_backup
        initializers = (init_history, init_active_trade_backup)
    for initialize in initializers:
        try:
            initialize()
        except Exception as exc:
            print('HISTORY_BACKUP_UNAVAILABLE:', getattr(initialize, '__name__', 'history_init'), type(exc).__name__, flush=True)

if __name__ == '__main__':
    main()
