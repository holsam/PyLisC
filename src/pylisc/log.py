'''
PyLisC: logging utilities
'''

# Import external libraries
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from loguru import logger

LOG_FORMAT = '<green>{time:YYYY-MM-DD HH:mm:ss}</> | <lvl>{level: <7}</> | {message}'
VERBOSITY_DICT = {0: 'WARNING', 1: 'INFO', 2: 'DEBUG'}

def configure_logger(batch_mode, input_path, output_mrc, output_dir, verbosity):
    # Configure log path
    if batch_mode:
        log_parent = output_dir
    else:
        log_parent = output_mrc.parent if output_mrc is not None else input_path.parent
    log_path = log_parent / f'pylisc_{datetime.now():%Y-%m-%d_%H-%M-%S}.log'

    # Define logging level
    log_level = VERBOSITY_DICT.get(verbosity)

    # Set up logger
    logger.remove()    # remove default handler
    logger.add(sys.stderr, format=LOG_FORMAT, level=log_level, colorize=True)    # add terminal logger 
    logger.add(log_path, format=LOG_FORMAT, level=log_level)    # add file logger

    # Logging confirmation
    logger.debug('logging configured: stderr and {}, level={}', log_path, log_level)

@contextmanager
def per_file_log(output_dir: Path, stem: str):
    '''
    Add a DEBUG-level sink at output_dir/stem.log, containing logs while inside this context, then remove sink on exit
    '''
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / f'{stem}.log'
    sink_id = logger.add(
        log_path,
        format=LOG_FORMAT,
        level='DEBUG',
        filter=lambda record, stem=stem: record['extra'].get('pylisc_file') == stem,
    )
    with logger.contextualize(pylisc_file=stem):
        try:
            yield log_path
        finally:
            logger.remove(sink_id)
