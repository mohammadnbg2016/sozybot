#!/usr/bin/python3

import concurrent.futures
import json
import time
from threading import Lock

import util
from route_updates import RouteMessage, route_callback_query
from tgapi import TelegramApi

update_id = 0
config = util.ConfigUtils()  # Create config file object
misc, plugins, database, extensions = util.init_package(config)
time_lock = Lock()
extension_lock = Lock()


def main():
    global update_id, misc, plugins, database
    url = "https://api.telegram.org/bot{}/getUpdates?offset={}".format(misc['token'], update_id)
    response = util.fetch(url, misc['session'])
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=config.workers)  # See docs
    executor.submit(check_time_args)
    try:
        response = response.json()
    except (AttributeError, ValueError) as e:
        print("Error parsing Telegram response: {}\nResponse: {}".format(e, response))
        time.sleep(config.sleep)
        return
    if response['ok'] and response['result']:  # Response ok and contains results
        update_id = response['result'][-1]['update_id'] + 1
        executor.submit(run_extension, response['result'])
        for result in response['result']:  # Loop through result
            if 'message' in result:  # For message updates
                executor.submit(RouteMessage(result['message'], misc, plugins, database).route_update)
            elif 'callback_query' in result:  # For callback query updates
                executor.submit(route_callback_query, result['callback_query'], database, plugins, misc)
    elif not response['ok']:
        print('Response not OK\nResponse: {}'.format(response))
    executor.shutdown(wait=False)  # returns immediately, sub processes will close by themselves
    time.sleep(config.sleep)  # Sleep for time defined in config


def check_time_args():
    with time_lock:
        time_args = database.select("flagged_time", ["plugin_name", "time", "plugin_data"])
        for argument in time_args:  # See if any plugins want to be activated at this time
            if argument['time'] <= time.time():
                plugin_name = argument['plugin_name']
                plugin_data = json.loads(argument['plugin_data']) if argument['plugin_data'] else None
                tg = TelegramApi(misc, database, plugin_name, plugin_data=plugin_data)
                plugins[plugin_name].main(tg)
                database.delete("flagged_time", argument)


def run_extension(result):
    with extension_lock:
        for extension in extensions.values():
            extension['data'] = extension['module'].main(result, database, extension['data'])


if __name__ == '__main__':
    while True:
        main()

