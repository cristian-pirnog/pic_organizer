from pathlib import Path
import click
import organizer
from pathlib import Path

@click.command('organize', no_args_is_help=True)
@click.argument('backup_dir', type=Path)
def organize(backup_dir: Path):
    organizer.process_directory(backup_dir)


if __name__ == '__main__':
    organize()