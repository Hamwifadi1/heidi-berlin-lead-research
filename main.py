"""Heidi AI Agent -- a clean rebuild with zero imported companies.

Commands:
  python main.py check-gemini
  python main.py run --limit 50 --max-pages 4 --max-queries 3
  python main.py export
  python main.py status
"""
import argparse
import sys
from heidi_agent.settings import config,DATABASE


def main():
    parser=argparse.ArgumentParser(description='Heidi Systems Berlin lead research agent (CLEAN database)')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('check-gemini',help='Small API health check; does not create a database')
    run=sub.add_parser('run',help='Discover, research and export; creates the DB only at first run')
    run.add_argument('--limit',type=int,default=10,help='Max company candidates to research this run')
    run.add_argument('--max-pages',type=int,default=4)
    run.add_argument('--max-queries',type=int,default=3)
    run.add_argument('--max-directory-links',type=int,default=400)
    sub.add_parser('export',help='Regenerate Excel + doc from this project local database; no API calls')
    sub.add_parser('status',help='Show DB counts, without creating anything')
    args=parser.parse_args()
    if args.command=='check-gemini':
        from heidi_agent.ai_extract import check_gemini
        cfg=config()
        print('[GEMINI CHECK]',check_gemini(cfg['gemini_key'],cfg['model']))
    elif args.command=='run':
        from heidi_agent.pipeline import run,export_from_db
        args.limit=max(1,min(args.limit,1000))
        args.max_pages=max(1,min(args.max_pages,8))
        args.max_queries=max(0,min(args.max_queries,50))
        args.max_directory_links=max(1,min(args.max_directory_links,1000))
        db=run(limit=args.limit,max_pages=args.max_pages,max_queries=args.max_queries,
               max_directory_links=args.max_directory_links)
        try:
            export_from_db(db)
        finally:
            db.close()
    elif args.command=='export':
        if not DATABASE.exists():
            print('[INFO] No database yet. Run research first. Nothing to export.')
            return 0
        from heidi_agent.storage import connect
        from heidi_agent.pipeline import export_from_db
        db=connect(DATABASE)
        try:
            export_from_db(db)
        finally:
            db.close()
    elif args.command=='status':
        if not DATABASE.exists():
            print('[STATUS] Clean project. No database, no research conducted yet.')
        else:
            from heidi_agent.storage import connect
            db=connect(DATABASE)
            try:
                for table in ('candidates','companies','facts','contacts','issues'):
                    print(f'{table}: {db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]}')
            finally:
                db.close()
    return 0

if __name__=='__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\n[STOP] Cancelled by user. Previously saved data remains in SQLite.')
        sys.exit(130)
    except Exception as exc:
        print(f'\n[ERROR] {type(exc).__name__}: {exc}')
        sys.exit(1)
