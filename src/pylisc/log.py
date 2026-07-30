import sys
from datetime import datetime
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
    logger.add(log_path, format=LOG_FORMAT, level='DEBUG')    # add file logger (always DEBUG)

    # Logging confirmation
    logger.debug('logging set up: stderr ({}) and {} ({})', log_level, log_path, 'DEBUG')