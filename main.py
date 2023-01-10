from pathlib import Path
import click
import organizer
from pathlib import Path

@click.group()
def cli():
    pass

@cli.command(no_args_is_help=True)
@click.argument('backup_dir', type=Path)
@click.option('--dry-run', is_flag=True)
def organize(backup_dir: Path, dry_run):
    organizer.process_directory(backup_dir, dry_run)

@cli.command(no_args_is_help=True)
@click.argument('backup_dir', type=Path)
@click.option('--dry-run', is_flag=True)
def refresh_checksums(backup_dir: Path, dry_run):
    organizer.refresh_checksums(backup_dir, dry_run)



if __name__ == '__main__':
    cli()