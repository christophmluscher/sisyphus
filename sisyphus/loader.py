import os
import logging
import importlib
import inspect
import asyncio
from ast import literal_eval
from importlib.machinery import PathFinder
import sisyphus.global_settings as gs


def load_config_file(config_name):
    import sisyphus.toolkit as toolkit

    # Check if file parameters are given
    if '(' in config_name:
        filename, parameters = config_name.split('(', 1)
        parameters, _ = parameters.rsplit(')', 1)
        parameters = literal_eval('(%s,)' % parameters)
    else:
        filename = config_name
        parameters = []

    toolkit.current_config_ = os.path.abspath(filename)
    toolkit.set_root_block(filename)

    filename = filename.replace(os.path.sep, '.')  # allows to use tab completion for file selection
    assert filename.split('.')[0] == "config", "Config files must be located in the config directory or named config.py: %s" % filename
    assert all(part.isidentifier() for part in filename.split('.')), "Config name is invalid: %s" % filename
    module_name, function_name = filename.rsplit('.', 1)
    try:
        config = importlib.import_module(module_name)
    except SyntaxError:
        import sys
        if gs.USE_VERBOSE_TRACEBACK:
            sys.excepthook = sys.excepthook_org
        raise

    f = res = None
    try:
        f = getattr(config, function_name)
    except AttributeError:
        if function_name != 'py':
            # If filename ends on py and no function is found we assume we should only read the config file
            # otherwise we reraise the exception
            raise

    if f:
        res = f(*parameters)

    task = None
    if inspect.iscoroutine(res):
        # Run till the first await command is found
        logging.info('Loading async config: %s' % config_name)
        loop = asyncio.get_event_loop()
        task = loop.create_task(res)
        loop.call_soon(loop.stop)
        loop.run_forever()
    else:
        logging.info('Loaded config: %s' % config_name)

    toolkit.current_config_ = None
    toolkit.all_config_readers.append((filename, task))
    return task


def load_configs(filenames=None):
    """

    :param filenames: list of strings containing the path to a config file, load default config if nothing is given
    :return: a dict containing all output paths registered in this config
    """
    if not filenames:
        if os.path.isfile(gs.CONFIG_FILE_DEFAULT):
            filenames = [gs.CONFIG_FILE_DEFAULT]
        elif os.path.isdir(gs.CONFIG_PREFIX):
            filenames = [gs.CONFIG_FUNCTION_DEFAULT]
    assert filenames, "Neither config file nor config directory exists"

    if isinstance(filenames, str):
        filenames = [filenames]

    for filename in filenames:
        load_config_file(filename)


class RecipeFinder:

    @classmethod
    def find_spec(cls, fullname, path, target=None):
        for rprefix, rdir in ((gs.RECIPE_PREFIX, gs.RECIPE_PATH), (gs.CONFIG_PREFIX, gs.CONFIG_PATH)):
            if fullname.startswith(rprefix):
                if path is None:
                    path = [os.path.abspath(rdir)]
                elif isinstance(path, str):
                    path = [os.path.abspath(os.path.join(rdir, path))]
                spec = PathFinder.find_spec(fullname, path, target)
                return spec

    @classmethod
    def invalidate_caches(cls):
        PathFinder.invalidate_caches()
