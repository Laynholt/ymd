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

number_of_workers = 5
chunk_of_tracks = 20

pathes = {'stuff': 'stuff'}
pathes = {
    'dirs': {
        'stuff': f'{pathes["stuff"]}',
        'download': 'download',
        'playlists_covers': f'{pathes["stuff"]}/playlists_covers'
    },

    'files': {
        'history': 'history.db',
        'default_playlist_cover': f'{pathes["stuff"]}/default_playlist_cover.jpg',
        'icon': f'{pathes["stuff"]}/icon.ico',
        'log': 'logging.log'
    }
}

__version__ = '0.3'
__data__ = '04.09.2022'
__github__ = 'https://github.com/Laynholt/ymd'
