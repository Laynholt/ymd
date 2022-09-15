"""
Copyright 2022 laynholt

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

NUMBER_OF_WORKERS = 5
CHUNK_OF_TRACKS = 20
LOGGER_DEBUG_MODE = True

paths = {'stuff': 'stuff'}
paths = {
    'dirs': {
        'stuff': f'{paths["stuff"]}',
        'download': 'download',
        'playlists_covers': f'{paths["stuff"]}/playlists_covers'
    },

    'files': {
        'history': f'{paths["stuff"]}/history.db',
        'default_playlist_cover': f'{paths["stuff"]}/default_playlist_cover.jpg',
        'icon': f'{paths["stuff"]}/icon.ico',
        'log': f'{paths["stuff"]}/logging.log'
    }
}

__version__ = '0.4'
__data__ = '09/2022'
__github__ = 'https://github.com/Laynholt/ymd'
