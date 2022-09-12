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

import tkinter
from tkinter import messagebox, filedialog, Menu
from tkinter.ttk import Combobox, Checkbutton, Progressbar, LabelFrame

import re
import os
import json
import math
import sqlite3
import asyncio
import threading
import webbrowser
from queue import Queue, Empty
from PIL import Image, ImageTk

import ahocorasick

from mutagen import File
from mutagen.id3 import TIT2, TPE1, TALB, APIC, TDRC, TRCK, TPOS, TPE2, TCON, USLT

from yandex_music import Client, Track, TracksList
from yandex_music.exceptions import YandexMusicError, UnauthorizedError, NetworkError

import config
from custom_formatter import CustomFormatter, logger_format
from session import YandexSession

import logging.config

logger = logging.getLogger(__name__)


def setup_logger(logger_type: int):
    logger.setLevel(logging.DEBUG)

    if os.path.exists(config.pathes['files']['log']):
        os.remove(config.pathes['files']['log'])

    file_handler = logging.FileHandler(config.pathes['files']['log'], encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(logger_format))
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    # console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(CustomFormatter())
    logger.addHandler(console_handler)


def strip_bad_symbols(text: str, soft_mode: bool = False) -> str:
    if soft_mode:
        result = re.sub(r"[^\w!@#$%^&)(_+}\]\[{,.;= -]", "", text)
    else:
        result = re.sub(r"[^\w_.)( -]", "", text)
    return result


class YandexMusicDownloader:
    def __init__(self):
        self.token = None
        self.history_database_path = None
        self.download_folder_path = None
        self.is_rewritable = None

    def start(self):
        """
        Метод, для запуска загрузчика
        :return:
        """
        try:
            if self._run_configuration_window():
                self._run_main_window()
        except NetworkError:
            messagebox.showerror('Ошибка', 'Не удалось подключиться к Yandex!\nПопробуйте позже.')

    def _run_configuration_window(self) -> bool:
        """
        Метод базовой настройки основных пармаетров загрузчика
        :return:
        """
        # Начальная инициализация основных полей
        config_filename = 'config.ini'
        self.token = ''
        self.history_database_path = config.pathes['files']['history']
        self.download_folder_path = config.pathes['dirs']['download']
        self.is_rewritable = False

        # Если существует файл конфигурации, то загружаемся с него
        if os.path.exists(config_filename) and os.path.isfile(config_filename):
            try:
                with open(config_filename, 'r', encoding='utf-8') as config_file:
                    try:
                        data = json.load(config_file)
                        self.token = data['token']
                        logger.debug(f'Из файла [{config_filename}] был получен токен: [{self.token}]')
                        self.history_database_path = data['history']
                        logger.debug(f'Из файла [{config_filename}] был получен токен: [{self.history_database_path}]')
                        self.download_folder_path = data['download']
                        logger.debug(f'Из файла [{config_filename}] был получен токен: [{self.download_folder_path}]')
                    except json.decoder.JSONDecodeError:
                        logger.error(f'Ошибка при разборе файла [{config_filename}]!')
                    except KeyError:
                        logger.error(f'Ошибка при попытке извлечь данные. '
                                     f'Видимо файл [{config_filename}] был ошибочно записан, либо некорректно изменён!')
            except IOError:
                logger.error(f'Не удалось открыть файл [{config_filename}] для чтения!')

        configuration_window = tkinter.Tk()
        configuration_window.geometry('550x220')
        try:
            configuration_window.iconbitmap(config.pathes["files"]["icon"])
        except tkinter.TclError:
            pass

        configuration_window.title('Yandex Music Downloader Configuration')
        configuration_window.resizable(width=False, height=False)

        labelframe_required = LabelFrame(configuration_window, text='Обязательное заполнение')
        labelframe_required.grid(column=0, row=0, columnspan=5, rowspan=2, padx=10, pady=10)

        label_enter_token = tkinter.Label(labelframe_required, text='Введите токен:')
        label_enter_token.grid(column=0, row=0, padx=5, pady=5)

        entry_enter_token = tkinter.Entry(labelframe_required, width=68)
        entry_enter_token.delete(0, tkinter.END)
        if len(self.token):
            entry_enter_token.insert(0, self.token)
        entry_enter_token.grid(column=1, row=0, columnspan=4, padx=5, pady=5)

        label_login_password = tkinter.Label(labelframe_required, text='Либо авторизуйтесь через логин и пароль:')
        label_login_password.grid(column=0, row=1, columnspan=2, padx=5, pady=5)

        # Обработчик гиперссылки
        def _callback(url):
            webbrowser.open_new(url)

        def _authorization():
            auth_window = tkinter.Toplevel(configuration_window)
            auth_window.geometry('470x250')
            try:
                auth_window.iconbitmap(config.pathes["files"]["icon"])
            except tkinter.TclError:
                pass

            auth_window.title('Окно авторизации')
            auth_window.resizable(width=False, height=False)

            label_info = tkinter.Label(auth_window, text='Вводимые Логин и Пароль нигде не сохраняются и никому '
                                                         'не передаются.\n'
                                                         'Они используюся для авторизации в аккаунте Яндекса и '
                                                         'получение токена,\n который в дальнейшем будет'
                                                         ' использоваться для скачивания медиафалов \nс Вашего аккаунта'
                                                         ' Яндекс Музыки.\n\nВесь исходный код данной программы'
                                                         ' доступен по ссылке на github:')
            label_info.grid(column=0, row=0, columnspan=5, rowspan=4, padx=15, pady=5)

            label_github = tkinter.Label(auth_window, text=f'{config.__github__}', fg='blue', cursor='hand2')
            label_github.grid(column=0, row=4, columnspan=5, padx=15, pady=5)
            label_github.bind('<Button-1>', lambda e: _callback(config.__github__))

            label_login = tkinter.Label(auth_window, text='Логин:')
            label_login.grid(column=2, row=5, padx=5, pady=5)

            entry_login = tkinter.Entry(auth_window, width=25)
            entry_login.grid(column=3, row=5, padx=5, pady=5)

            label_password = tkinter.Label(auth_window, text='Пароль:')
            label_password.grid(column=2, row=6, padx=5, pady=5)

            entry_password = tkinter.Entry(auth_window, width=25)
            entry_password.grid(column=3, row=6, padx=5, pady=5)

            def _auth():
                login = entry_login.get()
                if login == '':
                    messagebox.showinfo('Инфо', 'Перед продолжением введите Логин!')
                    return
                password = entry_password.get()
                if password == '':
                    messagebox.showinfo('Инфо', 'Перед продолжением введите Пароль!')
                    return

                ys = YandexSession(login=login, password=password)
                loop = asyncio.get_event_loop()
                response = loop.run_until_complete(ys.get_music_token())

                if response.get_error() is not None:
                    messagebox.showerror('Ошибка', f'{response.get_error()}')
                    return

                if response.get_token() is None:
                    messagebox.showerror('Ошибка', 'Не удалось получить токен!')
                    return

                self.token = response.get_token()
                entry_enter_token.delete(0, tkinter.END)
                entry_enter_token.insert(0, self.token)

                auth_window.destroy()

            button_auth = tkinter.Button(auth_window, text='Войти', command=_auth, width=15)
            button_auth.grid(column=3, row=7, padx=5, pady=5)

        button_login_password = tkinter.Button(labelframe_required, text='Авторизоваться', command=_authorization)
        button_login_password.grid(column=2, row=1, padx=5, pady=5)

        label_how_get_token = tkinter.Label(labelframe_required, text='Как получить токен?', fg='blue', cursor='hand2')
        label_how_get_token.grid(column=4, row=1, sticky=tkinter.E, padx=5, pady=5)

        label_how_get_token.bind('<Button-1>', lambda e: _callback("https://github.com/MarshalX/yandex-music-api/"
                                                                   "discussions/513#discussioncomment-2729781"))

        labelframe_optional = LabelFrame(configuration_window, text='Опциональное заполнение')
        labelframe_optional.grid(column=0, row=2, columnspan=5, rowspan=2, padx=10, pady=10)

        # Выбираем файл базы данных
        def _choose_database():
            database = filedialog.askopenfilename(
                title="Укажите файл базы данных",
                filetypes=[("Все файлы", "*.db*")]
            )
            if database != "":
                self.history_database_path = os.path.abspath(database)
            logger.debug(f'Файл базы данных установлен на: [{self.history_database_path}].')

        button_history = tkinter.Button(labelframe_optional, text='Указать БД', command=_choose_database)
        button_history.grid(column=0, row=2, padx=5, pady=5)

        # Выбираем папку, куда качать
        def _choose_download():
            folder = filedialog.askdirectory(title="Выберете папку Загрузки")
            if folder != "":
                self.download_folder_path = os.path.abspath(folder)
            logger.debug(f'Папка загрузки установлена на: [{self.download_folder_path}].')

        button_download = tkinter.Button(labelframe_optional, text='Указать папку Download', command=_choose_download)
        button_download.grid(column=1, row=2, padx=5, pady=5)

        check_is_rewritable = tkinter.BooleanVar()
        check_is_rewritable.set(self.is_rewritable)
        checkbutton_rewritable = Checkbutton(labelframe_optional, text='Перезаписывать существующие композиции',
                                             var=check_is_rewritable)
        checkbutton_rewritable.grid(column=2, row=2, padx=5, pady=5)

        # Экшен, для установки значений по умолчанию
        def _reset_all():
            self.token = ''
            entry_enter_token.delete(0, tkinter.END)
            self.history_database_path = config.pathes['files']['history']
            self.download_folder_path = config.pathes['dirs']['download']
            logger.debug(f'Токен установлен в [{self.token}].')
            logger.debug(f'Путь к файлу базы данных установлен в [{self.history_database_path}].')
            logger.debug(f'Путь к папке Загрузки установлен в [{self.download_folder_path}].')
            check_is_rewritable.set(self.is_rewritable)

        button_reset = tkinter.Button(configuration_window, text='Сбросить всё', command=_reset_all)
        button_reset.grid(column=0, row=4, padx=10, pady=5, sticky=tkinter.W)

        is_continue = False

        # Экшен, для перехода на главное окно приложения
        def _continue_action():
            if entry_enter_token.get() == '':
                messagebox.showinfo('Инфо', 'Перед продолжением необходимо ввести токен!')
                return
            self.token = entry_enter_token.get()
            self.is_rewritable = check_is_rewritable.get()

            try:
                with open(config_filename, 'w', encoding='utf-8') as config_file1:
                    data1 = {
                        'token': self.token,
                        'history': self.history_database_path,
                        'download': self.download_folder_path
                    }
                    json.dump(data1, config_file1)
                    logger.debug(f'Значения токена: [{self.token}], пути к базе данных: [{self.history_database_path}] '
                                 f'и пути к папке скачивания: [{self.download_folder_path}] были записаны в файл: '
                                 f'[{config_filename}].')
            except IOError:
                logger.error(f'Не удалось открыть файл [{config_filename}] для записи!')
            nonlocal is_continue
            is_continue = True
            configuration_window.destroy()

        button_continue = tkinter.Button(configuration_window, text='Продолжить', command=_continue_action)
        button_continue.grid(column=4, row=4, padx=10, pady=5, sticky=tkinter.E)

        configuration_window.mainloop()
        return is_continue

    def _run_main_window(self):
        """
        Метод работы основного окна
        :return:
        """
        self.main_thread_state = True
        self.mutex = threading.Lock()
        self.playlists_covers_folder_name = config.pathes['dirs']['playlists_covers']

        self.number_of_workers = config.number_of_workers
        self.chunk_of_tracks = config.chunk_of_tracks

        self.main_window = tkinter.Tk()
        self.main_window.geometry('550x170')
        try:
            self.main_window.iconbitmap(config.pathes["files"]["icon"])
        except tkinter.TclError:
            pass

        self.main_window.title('Yandex Music Downloader')
        self.main_window.resizable(width=False, height=False)

        self.client = None
        self.playlists = []
        self.liked_tracks = []
        self.downloading_or_updating_playlists = {}
        self.partial_downloading_or_updating_tracks = {}

        # Загружаем все пользовательские данные
        thread = threading.Thread(target=self._load_all_account_info)
        thread.start()

        def _about():
            about_window = tkinter.Toplevel(self.main_window)
            about_window.geometry('250x90')
            about_window.title('О программе')
            try:
                about_window.iconbitmap(config.pathes["files"]["icon"])
            except tkinter.TclError:
                pass
            about_window.resizable(width=False, height=False)

            label_about = tkinter.Label(about_window, text=f'Версия: {config.__version__};\n'
                                                           f'Написал laynholt в {config.__data__};\n'
                                                           f'Репозиторий:')
            label_about.grid(column=0, row=0, padx=20, pady=5, columnspan=2, sticky=tkinter.E)

            label_git = tkinter.Label(about_window, text=f'https://github.com/Laynholt/ymd', fg='blue', cursor='hand2')
            label_git.grid(column=0, row=1, padx=20, columnspan=2, sticky=tkinter.E)

            # Обработчик гиперссылки
            def _callback(url):
                webbrowser.open_new(url)

            label_git.bind('<Button-1>', lambda e: _callback(config.__github__))

        self.menu_main = Menu(self.main_window)
        self.main_window.config(menu=self.menu_main)

        self.menu_help = Menu(self.menu_main, tearoff=0)
        self.menu_help.add_command(label='О программе', command=_about)

        self.menu_additional = Menu(self.menu_main, tearoff=0)
        self.menu_additional.add_command(label='Обновить метаданные треков текущего плейлиста',
                                         command=lambda: self._wrapper_download_or_update_tracks(update_mode=True))
        self.menu_additional.add_command(label='Добавить текущий плейлист в базу (без скачивания треков)',
                                         command=lambda: self._wrapper_download_or_update_tracks(
                                             only_add_to_database=True))
        self.menu_additional.add_separator()
        self.menu_additional.add_command(label='Выборочно скачать треки из текущего плейлиста',
                                         command=lambda: self._partial_download_or_update_playlist())
        self.menu_additional.add_command(label='Выборочно обновить треки из текущего плейлиста',
                                         command=lambda: self._partial_download_or_update_playlist(update_mode=True))
        self.menu_additional.add_separator()
        self.check_id_in_name = tkinter.BooleanVar()
        self.check_id_in_name.set(False)
        self.menu_additional.add_checkbutton(label='Добавить id трека в название (позволит качать треки с одинаковыми '
                                                   'названиями)',
                                             onvalue=1, offvalue=0, variable=self.check_id_in_name)
        is_rewritable = self.is_rewritable
        self.is_rewritable = tkinter.BooleanVar()
        self.is_rewritable.set(is_rewritable)
        self.menu_additional.add_checkbutton(label='Перезаписывать существующие треки',
                                             onvalue=1, offvalue=0, variable=self.is_rewritable)

        self.menu_main.add_cascade(label='Дополнительно', menu=self.menu_additional)
        self.menu_main.add_cascade(label='Справка', menu=self.menu_help)

        current_playlist_cover = ImageTk.PhotoImage(Image.open(config.pathes['files']['default_playlist_cover']))
        self.label_playlist_cover = tkinter.Label(self.main_window, image=current_playlist_cover)
        self.label_playlist_cover.grid(column=0, row=0, rowspan=3, sticky=tkinter.W, padx=15, pady=5)

        self.label_playlist_names = tkinter.Label(self.main_window, text='Выберете плейлист для скачивания:')
        self.label_playlist_names.grid(column=1, row=0, columnspan=2, sticky=tkinter.W, pady=5)

        # Реагируем на изменения в комбобоксе и вызываем метод отбновления обложки
        def _combo_was_updated(value) -> bool:
            self._change_current_playlist_cover()
            return True

        self.combo_playlists = Combobox(self.main_window, width=40, validate='focusout',
                                        validatecommand=(self.main_window.register(_combo_was_updated), '%P'))
        self.combo_playlists.bind('<<ComboboxSelected>>', _combo_was_updated)
        self.combo_playlists['state'] = 'readonly'
        self.combo_playlists.grid(column=1, row=1, columnspan=2, sticky=tkinter.W)

        self.label_track_number_text = tkinter.Label(self.main_window, text='Количество треков в плейлисте:')
        self.label_track_number_text.grid(column=1, row=2, columnspan=2, sticky=tkinter.W, pady=5)

        self.check_state_history = tkinter.BooleanVar()
        self.check_state_history.set(True)
        self.check_history = Checkbutton(self.main_window, text='Скачать только новые треки (нужна history.db)',
                                         var=self.check_state_history)
        self.check_history.grid(column=0, row=3, columnspan=3, sticky=tkinter.W, padx=10)

        self.button_download = tkinter.Button(self.main_window, width=15, text='Скачать',
                                              command=lambda: self._wrapper_download_or_update_tracks())
        self.button_download.grid(column=3, row=3)

        # Изменяем правило, при закрытие окна
        def _prepare_to_close_main_program():
            self.main_thread_state = False
            messagebox.showinfo('Инфо', 'Подождите, программа завершается...')
            logger.debug('Идет завершение программы...')

            main_thread = threading.current_thread()
            alive_threads = threading.enumerate()
            for _thread in alive_threads:
                if _thread is main_thread:
                    logger.debug(f'Основной поток [{main_thread.ident}] ожидает завершения всех дочерних.')
                    continue
                _thread_id = _thread.ident
                logger.debug(f'Ожидание заверешния потока [{_thread_id}]')
                _thread.join()
                logger.debug(f'Поток [{_thread_id}] был завершён.')
            logger.debug('Все потоки завершены. Завершение основного потока...')
            self.main_window.destroy()

        self.main_window.protocol("WM_DELETE_WINDOW", _prepare_to_close_main_program)
        self.main_window.mainloop()

    def _partial_download_or_update_playlist(self, update_mode: bool = False):
        current_playlist_index = self.combo_playlists.current()
        if current_playlist_index == -1:
            logger.error('Список плейлистов пуст!')
            messagebox.showerror('Ошибка', 'Список плейлистов пуст!')
            return

        try:
            playlist = self.playlists[current_playlist_index]
            current_playlist = self.client.users_playlists(kind=playlist.kind)
        except YandexMusicError:
            logger.error('Не удалось подключиться к Yandex!')
            messagebox.showerror('Ошибка', 'Не удалось подключиться к Yandex!\nПопробуйте позже.')
            return

        partial_window = tkinter.Toplevel(self.main_window)
        partial_window.geometry('520x280')
        try:
            partial_window.iconbitmap(config.pathes["files"]["icon"])
        except tkinter.TclError:
            pass

        partial_window.title('Yandex Music Downloader')
        partial_window.resizable(width=False, height=False)

        def _close_window():
            try:
                del self.partial_downloading_or_updating_tracks[playlist.kind]
                logger.debug(f'Список частичного скачивания/обновления для плейлиста [{playlist.title}] был удалён.')
            except KeyError:
                logger.error(f'Не удалось удалить список частичной загрузки/обновления для плейлиста [{playlist.title}]!')
            logger.debug(f'Ожидаю завершения потока [{thread.ident}].')
            thread.join()
            logger.debug('Закрываю окно.')
            partial_window.destroy()

        partial_window.protocol("WM_DELETE_WINDOW", _close_window)

        auto = ahocorasick.Automaton()
        tracks_names = []

        # Запоминаем все названия композиций, для дальнейшего поиска в них
        def _load_pattern_strings():
            for index, track in enumerate(current_playlist.tracks):
                track = track.track
                track_artists = ', '.join(i['name'] for i in track.artists)
                track_title = track.title + ("" if track.version is None else f' ({track.version})')
                track_name = f'{track_artists} - {track_title}'

                if track_name not in tracks_names:
                    tracks_names.append(track_name)

        thread = threading.Thread(target=_load_pattern_strings)
        thread.start()

        label_search = tkinter.Label(partial_window, text='Поиск:')
        label_search.grid(column=0, row=0, sticky=tkinter.E, padx=10, pady=10)

        # Ищем композиции по паттерну
        def _show_same_tracks_names(pattern: str):
            logger.debug(f'Начинаю поиск сходства по шаблону [{pattern}].')
            auto.add_word(pattern.lower(), pattern.lower())
            auto.make_automaton()

            track_list = []
            for track_name in tracks_names:
                for end_ind, found in auto.iter(track_name.lower()):
                    track_list.append(track_name)
                    logger.debug(f'Найдено совпадение для трека [{track_name}] в [{track_name}] c шаблоном [{pattern}].')

            track_list.sort()
            for track_name in track_list:
                listbox_pattern_tracks.insert(tkinter.END, track_name)

            auto.remove_word(pattern)

        def _entry_callback(value: tkinter.StringVar):
            listbox_pattern_tracks.delete(0, tkinter.END)
            _show_same_tracks_names(value.get())

        entry_string_variable = tkinter.StringVar()
        entry_string_variable.trace_add("write", lambda name, index, mode, sv=entry_string_variable: _entry_callback(sv))
        entry_search_track = tkinter.Entry(partial_window, width=40, textvariable=entry_string_variable)
        entry_search_track.grid(column=1, row=0, columnspan=2, sticky=tkinter.EW, padx=10, pady=10)

        frame = tkinter.Frame(partial_window)
        frame.grid(column=0, row=1, columnspan=3, padx=10, pady=10)

        scrollbar = tkinter.Scrollbar(frame)
        scrollbar.grid(column=2, row=0, sticky=tkinter.NS)

        listbox_pattern_tracks = tkinter.Listbox(frame, width=80, selectmode="multiple", yscrollcommand=scrollbar.set)
        listbox_pattern_tracks.grid(column=0, row=0, columnspan=2)
        scrollbar.config(command=listbox_pattern_tracks.yview)

        def _add_to_list():
            selected = listbox_pattern_tracks.curselection()
            if len(selected) != 0:
                for sel in selected:
                    selected_item = listbox_pattern_tracks.get(sel)

                    logger.debug(f'Начинаю добавление трека [{selected_item}] в список.')
                    for track in current_playlist.tracks:
                        track = track.track
                        track_artists = ', '.join(i['name'] for i in track.artists)
                        track_title = track.title + ("" if track.version is None else f' ({track.version})')
                        track_name = f'{track_artists} - {track_title}'

                        if selected_item == track_name:
                            if current_playlist.kind not in self.partial_downloading_or_updating_tracks:
                                self.partial_downloading_or_updating_tracks.update({
                                    current_playlist.kind: [track]
                                })
                                logger.debug(f'Создан список частичного скачивания/обновления для плейлиста '
                                             f'[{current_playlist.title}]. Был добавлен трек [{track_name}].')
                                button_download_or_update_tracks['state'] = 'normal'
                            else:
                                if track not in self.partial_downloading_or_updating_tracks[current_playlist.kind]:
                                    self.partial_downloading_or_updating_tracks[current_playlist.kind].append(track)
                                    logger.debug(f'Трек [{track_name}] добавлен в список для плейлиста '
                                                 f'[{current_playlist.title}]')
                                else:
                                    logger.debug(f'Трек [{track_name}] уже добавлен в список для плейлиста '
                                                 f'[{current_playlist.title}]')
                            break

        def _remove_from_list():
            selected = listbox_pattern_tracks.curselection()
            if len(selected) != 0:
                for sel in selected:
                    selected_item = listbox_pattern_tracks.get(sel)

                    logger.debug(f'Начинаю удаление трека [{selected_item}] из списока.')
                    for track in self.partial_downloading_or_updating_tracks[current_playlist.kind]:
                        track_artists = ', '.join(i['name'] for i in track.artists)
                        track_title = track.title + ("" if track.version is None else f' ({track.version})')
                        track_name = f'{track_artists} - {track_title}'

                        if selected_item == track_name:
                            self.partial_downloading_or_updating_tracks[current_playlist.kind].remove(track)
                            logger.debug(f'Трек [{track_name}] удалён из списка плейлиста [{current_playlist.title}].')

                            if len(self.partial_downloading_or_updating_tracks[current_playlist.kind]) == 0:
                                del self.partial_downloading_or_updating_tracks[current_playlist.kind]
                                logger.debug(f'Список для частичного скачивания/обновления для плейлиста '
                                             f'[{current_playlist.title}] был удалён.')
                                button_download_or_update_tracks['state'] = 'disable'
                            break

        button_add_current_track = tkinter.Button(partial_window, text='Добавить в список', width=20,
                                                  command=_add_to_list)
        button_add_current_track.grid(column=1, row=2, padx=10, pady=10)

        button_remove_current_track = tkinter.Button(partial_window, text='Удалить из списока', width=20,
                                                     command=_remove_from_list)
        button_remove_current_track.grid(column=0, row=2, padx=10, pady=10)

        text = 'Скачать' if not update_mode else 'Обновить'
        button_download_or_update_tracks = tkinter.Button(partial_window, text=f'{text}', width=20,
                                                          command=lambda: self._wrapper_download_or_update_tracks(
                                                              update_mode=update_mode,
                                                              partial_mode=True
                                                          ))
        button_download_or_update_tracks['state'] = 'disable'
        button_download_or_update_tracks.grid(column=2, row=2, padx=10, pady=10)

    def _create_stuff_directories(self):
        """
        Создаём нужны директории для работы:
            1) Директорию для дефолтной обложки плейлиста и её, если нет
            2) Директорию, где будем хранить все обложки плейлистов
        :return:
        """
        # Если нет дефолного изображения альбома, то создаем его
        default_playlist_cover = config.pathes['files']['default_playlist_cover']
        if not os.path.exists(default_playlist_cover):
            img = Image.new('RGB', (100, 100), color=(73, 109, 137))

            stuff_directory = config.pathes['dirs']['stuff']
            if not os.path.exists(stuff_directory) or os.path.isfile(stuff_directory):
                os.makedirs(stuff_directory, exist_ok=True)
                logger.debug(f'Служебная директория была содана по пути [{stuff_directory}].')
            img.save(default_playlist_cover)
            logger.debug(f'Дефолтная обложка не была найдена, поэтому была создана занова и сохранена по пути '
                         f'[{default_playlist_cover}]!')

        # Если папки с обложками не существует, то создаем
        if not os.path.exists(self.playlists_covers_folder_name) or os.path.isfile(self.playlists_covers_folder_name):
            os.makedirs(self.playlists_covers_folder_name, exist_ok=True)
            logger.debug(f'Была создана папка [{self.playlists_covers_folder_name}] для хранения обложек плейлистов.')
        else:
            logger.debug('Папка для обложек уже сущестует.')

    def _load_all_account_info(self):
        """
        Загружаем название плейлистов, обложки и тд. + обновляем состояние всех виджетов
        :return:
        """
        try:
            # Проверяем введённый токен на валидность
            try:
                self.client = Client(token=self.token)
                self.client.init()
                logger.debug('Введённый токен валиден, авторизация прошла успешно!')
            except UnauthorizedError:
                logger.error('Введен невалидный токен!')
                messagebox.showerror('Ошибка', 'Введенный токен невалиден!')
                self.main_window.destroy()
                return

            self.playlists = self.client.users_playlists_list()
            self.liked_tracks = self.client.users_likes_tracks()

            # Создаем рабочие директории
            self._create_stuff_directories()

            # Скачиваем все обложки всех плейлистов
            thread = threading.Thread(target=self._download_all_playlists_covers)
            thread.start()

            # Заполняем комбо названиями плейлистов
            for playlist in self.playlists:
                self.combo_playlists['values'] = (*self.combo_playlists['values'], f'{playlist.title}')
            self.combo_playlists.current(0)

            # Изменияем текущую отображающуюся обложку плейлиста
            self._change_current_playlist_cover()

            # Создание необходимых таблиц в базе данных
            self._database_create_tables()
        except NetworkError:
            messagebox.showerror('Ошибка', 'Не удалось подключиться к Yandex!\nПопробуйте позже.')

    def _download_all_playlists_covers(self):
        """
        Скачиваем все обложки всех плейлистов
        :return:
        """
        for playlist in self.playlists:
            if playlist.cover:
                if playlist.cover.items_uri is not None:
                    playlist_title = strip_bad_symbols(playlist.title)
                    if not os.path.exists(f'{self.playlists_covers_folder_name}/{playlist_title}.jpg'):
                        try:
                            playlist.cover.download(
                                filename=f'{self.playlists_covers_folder_name}/{playlist_title}.jpg',
                                size='100x100')
                            logger.debug(f'Обложка для плейлиста [{playlist_title}] была загружена в '
                                         f'[{self.playlists_covers_folder_name}/{playlist_title}.jpg].')
                        except NetworkError:
                            messagebox.showerror('Ошибка', 'Не удалось подключиться к Yandex!\nПопробуйте позже.')
                            return
                    else:
                        logger.debug(f'Обложка для плейлиста [{playlist_title}] уже существует в '
                                     f'[{self.playlists_covers_folder_name}/{playlist_title}.jpg].')

    def _change_current_playlist_cover(self):
        """
        Меняем отображающуюся текущую обложку плейлиста
        :return:
        """
        current_playlist_index = self.combo_playlists.current()
        if current_playlist_index == -1:
            return

        current_playlist = self.playlists[current_playlist_index]
        playlist_title = strip_bad_symbols(current_playlist.title)

        filename = config.pathes['files']['default_playlist_cover']
        if current_playlist.cover:
            if current_playlist.cover.items_uri is not None:
                if not os.path.exists(f'{self.playlists_covers_folder_name}/{playlist_title}.jpg'):
                    logger.debug(f'Обложка для плейлиста [{playlist_title}] не была найдена, начинаю загрузку.')
                    current_playlist.cover.download(
                        filename=f'{self.playlists_covers_folder_name}/{playlist_title}.jpg',
                        size='100x100')
                    logger.debug(f'Обложка для плейлиста [{playlist_title}] была загружена в '
                                 f'[{self.playlists_covers_folder_name}/{playlist_title}.jpg].')
                filename = f'{self.playlists_covers_folder_name}/{playlist_title}.jpg'

        current_playlist_cover = ImageTk.PhotoImage(Image.open(filename))
        self.label_playlist_cover.configure(image=current_playlist_cover)
        self.label_playlist_cover.image = current_playlist_cover

        text = self.label_track_number_text['text'].split(':')[0]
        self.label_track_number_text.config(text=f'{text}: {current_playlist.track_count}')
        logger.debug(f'Текущая обложка изменена на [{playlist_title}].')

    def _wrapper_download_or_update_tracks(self, update_mode: bool = False, partial_mode: bool = False,
                                           only_add_to_database: bool = False):
        """
        Обработчик, который вызывается при нажатии на кнопку скачать или обновить
        :param update_mode: признак обновления метаданных
        :param partial_mode: признак выборочного скачивания
        :param only_add_to_database: признак добавления только в бд
        :return:
        """
        if len(self.playlists) == 0:
            messagebox.showinfo('Инфо', 'Список ваших плейлистов пока пуст!\n\n'
                                        'Создайте плейлист на Яндекс Музыке, добавьте в него нужные композиции и'
                                        ' попробуйте ещё раз.')
            return

        playlist = self.playlists[self.combo_playlists.current()]
        if playlist.kind not in self.downloading_or_updating_playlists:
            if playlist.track_count == 0:
                messagebox.showinfo('Инфо', 'Данный плейлист пуст!')
                return

            thread = threading.Thread(target=self._download_or_update_all_tracks, args=(
                self.combo_playlists.current(), self.check_state_history.get(), update_mode, partial_mode,
                only_add_to_database,))

            info = 'скачивания'
            if update_mode:
                info = 'обновления метаданных треков для'
            elif only_add_to_database:
                info = 'добавления треков в базу данных для'
            elif partial_mode:
                info = 'частичного скачивания'
            logger.debug(f'Создаю новый поток для {info} плейлиста [{playlist.title}]')
            thread.start()
        else:
            logger.debug(f'Загрузка или обновление плейлиста {playlist.title} уже производится на данный момент!')
            messagebox.showinfo('Инфо', f'Подождите, загрузка или обновление плейлиста {playlist.title}'
                                        f' уже производится на данный момент!')

    def _download_or_update_all_tracks(self, playlist_index: int, download_only_new: bool, update_mode: bool,
                                       partial_mode: bool, only_add_to_database: bool):
        """
        Метод для скачивания или обновления метаданных всех композиций из выбранного плейлиста
        :param playlist_index: номер плейлиста в комбобоксе
        :param download_only_new: флаг на скачивания только новых композиций (чекбокс)
        :param update_mode: флаг обновления метаданных треков
        :param partial_mode: флаг для частичного скачивания треков
        :param only_add_to_database:  флаг для добавления только в бд
        :return:
        """
        # Создаем дочернее окно для визуализации прогресса скачивания

        playlist = self.playlists[playlist_index]

        info = 'скачивания'
        if update_mode:
            info = 'обновления метаданных треков'
        elif only_add_to_database:
            info = 'добавления треков в базу данных'
        elif partial_mode:
            info = 'частичного скачивания'
        logger.debug(f'Поток [{threading.get_ident()}] для {info} плейлиста [{playlist.title}] был создан!')
        child_thread_state = True
        try:
            child_window = tkinter.Toplevel(self.main_window)
            child_window.geometry('400x100')
            child_window.resizable(width=False, height=False)
            try:
                child_window.iconbitmap(config.pathes["files"]["icon"])
            except tkinter.TclError:
                pass
            child_window.title(f'{playlist.title}')
            child_window.protocol("WM_DELETE_WINDOW", lambda: None)

            progress_bar = Progressbar(child_window, orient='horizontal', mode='determinate', length=380)
            progress_bar.grid(column=0, row=0, columnspan=2, padx=10, pady=20)

            label_value = tkinter.Label(child_window, text=f'Прогресс {info}: {0 / playlist.track_count} [0 %]')
            label_value.grid(column=0, row=1, columnspan=2)

            # Код для закачки и обновления файлов
            current_playlist = self.client.users_playlists(kind=playlist.kind)
            playlist_title = strip_bad_symbols(current_playlist.title)

            filename = ''
            try:
                download_folder_path = f'{self.download_folder_path}/{playlist_title}'
                if os.path.exists(download_folder_path):
                    logger.debug(f'Директория [{download_folder_path}] уже существует.')
                else:
                    logger.debug(f'Директория [{download_folder_path}] была создана.')
                os.makedirs(f'{download_folder_path}', exist_ok=True)

                if os.path.exists(f'{download_folder_path}/covers'):
                    logger.debug(f'Директория [{download_folder_path}/covers] уже существует.')
                else:
                    logger.debug(f'Директория [{download_folder_path}/covers] была создана.')
                os.makedirs(f'{download_folder_path}/covers', exist_ok=True)

                if os.path.exists(f'{download_folder_path}/info'):
                    logger.debug(f'Директория [{download_folder_path}/info] уже существует.')
                else:
                    logger.debug(f'Директория [{download_folder_path}/info] была создана.')
                os.makedirs(f'{download_folder_path}/info', exist_ok=True)

                if not update_mode:
                    filename = {
                        'e': f'{download_folder_path}/info/download_errors-{playlist_title}.txt',
                        'd': f'{download_folder_path}/info/downloaded_tracks-{playlist_title}.txt'
                    }
                    with open(filename['e'], 'w', encoding='utf-8') as file:
                        pass
                    with open(filename['d'], 'w', encoding='utf-8') as file:
                        pass

                track_count = current_playlist.track_count if not partial_mode else\
                    len(self.partial_downloading_or_updating_tracks[playlist.kind])

                # Добавляем в словарь номер плейлиста и его обработчик
                self.downloading_or_updating_playlists.update({playlist.kind: self.DownloaderHelper(
                    progress_bar=progress_bar,
                    label_value=label_value,
                    download_folder_path=download_folder_path,
                    history_database_path=self.history_database_path,
                    is_rewritable=self.is_rewritable.get(),
                    download_only_new=download_only_new,
                    filenames=filename,
                    playlist_title=playlist_title,
                    number_tracks_in_playlist=track_count,
                    liked_tracks=self.liked_tracks,
                    add_track_id_to_name=self.check_id_in_name.get(),
                    main_thread_state=lambda: self.main_thread_state,
                    child_thread_state=lambda: child_thread_state,
                    update_mode=update_mode,
                    only_add_to_database=only_add_to_database
                )})

                info = f'Загрузка треков плейлиста [{current_playlist.title}] начата!'
                if update_mode:
                    info = f'Обновление метаданных треков плейлиста [{current_playlist.title}] начато!'
                elif only_add_to_database:
                    info = f'Добавления в базу данных треков плейлиста [{current_playlist.title}] начато!'
                elif partial_mode:
                    info = f'Частичная загрузка треков плейлиста [{current_playlist.title}] начата!'
                messagebox.showinfo('Инфо', f'{info}')

                queue = Queue()
                workers = []

                for x in range(self.number_of_workers):
                    workers.append(self.DownloaderWorker(queue, self.downloading_or_updating_playlists[playlist.kind]))
                    workers[x].daemon = True
                    workers[x].start()

                def _close_program():
                    nonlocal child_thread_state
                    child_thread_state = False
                    info1 = 'загрузки скачиваемых на данный момент треков.'
                    if update_mode:
                        if update_mode:
                            info1 = 'обновления метаданных текущих треков.'
                        elif only_add_to_database:
                            info1 = 'добавления текущих треков в базу данных'
                    messagebox.showinfo('Инфо', f'Подождите, окно закроется по завершению {info1}')

                    for _worker in workers:
                        logger.debug(f'Поток [{_worker.ident}] был поставлен на завершение.')
                        _worker.is_finished = True
                    for _worker in workers:
                        _worker_id = _worker.ident
                        logger.debug(f'Ожидание завершения потока [{_worker_id}].')
                        _worker.join()
                        logger.debug(f'Поток [{_worker_id}] был завершён.')
                    child_window.destroy()

                child_window.protocol("WM_DELETE_WINDOW", _close_program)

                logger.debug(f'Начало добавления треков в очередь на выполнения для плейлиста [{playlist_title}].')
                for i in range(math.ceil(track_count / self.chunk_of_tracks)):
                    number_of_tracks_was_added = 0
                    for j in range(i * self.chunk_of_tracks, (1 + i) * self.chunk_of_tracks):
                        number_of_tracks_was_added = j
                        if j == track_count:
                            break
                        if not partial_mode:
                            queue.put(current_playlist.tracks[j].track)
                        else:
                            queue.put(self.partial_downloading_or_updating_tracks[playlist.kind][j])
                    logger.debug(f'В очередь для плейлиста [{playlist_title}] было добавлено '
                                 f'{number_of_tracks_was_added} треков.')
                    queue.join()
                    logger.debug(f'Итерация №{i} для плейлиста [{playlist_title}] была выполена '
                                 f'с {number_of_tracks_was_added} треками.')

                    if not self.main_thread_state:
                        logger.debug('Основное окно получило сигнал на завершение, начинаю подготовку '
                                     'к прекращению работы.')
                        break

                    if not child_thread_state:
                        logger.debug('Окно загрузки получило сигнал на завершение, начинаю подготовку '
                                     'к прекращению работы.')
                        break

                    if YandexMusicDownloader.DownloaderWorker.is_network_error:
                        logger.error('Возникла ошибка с подключением к Яндекс Музыке, начинаю подготовку '
                                     'к прекращению работы.')
                        break
                else:

                    if update_mode:
                        logger.debug(f'Обновление метаданных для треков для плейлиста '
                                     f'[{playlist_title}] завершено. Обновлено '
                                     f'[{self.downloading_or_updating_playlists[playlist.kind].analyzed_and_downloaded_tracks["u"]}]'
                                     f' трека(ов).')
                    elif only_add_to_database:
                        logger.debug(f'Добавление в базу данных треков для плейлиста '
                                     f'[{playlist_title}] завершено. Добавлено '
                                     f'[{self.downloading_or_updating_playlists[playlist.kind].analyzed_and_downloaded_tracks["u"]}]'
                                     f' трека(ов).')
                    else:
                        logger.debug(f'Загрузка треков для плейлиста '
                                     f'[{playlist_title}] завершена. Загружено '
                                     f'[{self.downloading_or_updating_playlists[playlist.kind].analyzed_and_downloaded_tracks["d"]}]'
                                     f' трека(ов).')

                for worker in workers:
                    logger.debug(f'Поток [{worker.ident}] был поставлен на завершение.')
                    worker.is_finished = True
                for worker in workers:
                    worker_id = worker.ident
                    logger.debug(f'Ожидание завершения потока [{worker_id}].')
                    worker.join()
                    logger.debug(f'Поток [{worker_id}] был завершён.')

                if not self.main_thread_state or not child_thread_state or \
                        YandexMusicDownloader.DownloaderWorker.is_network_error:
                    logger.debug('Завершаю работу.')
                else:
                    if update_mode:
                        if self.downloading_or_updating_playlists[playlist.kind]. \
                                analyzed_and_downloaded_tracks['u'] > 0:
                            messagebox.showinfo('Инфо',
                                                f'Обновление треков плейлиста [{current_playlist.title}] закончено!\n'
                                                f'Обновлено [{self.downloading_or_updating_playlists[playlist.kind].analyzed_and_downloaded_tracks["u"]}] трека(ов).\n'
                                                f'Не удалось обновить [{self.downloading_or_updating_playlists[playlist.kind].analyzed_and_downloaded_tracks["e"]}] трека(ов).')
                        else:
                            messagebox.showinfo('Инфо',
                                                f'На диске не найдено подходящих треков из плейлиста [{current_playlist.title}] для обновления!\n\n'
                                                f'Попробуйте сначала скачать данный плейлист, либо поставить '
                                                f'галочку напротив "id трека в названии".')
                    elif only_add_to_database:
                        if self.downloading_or_updating_playlists[playlist.kind]. \
                                analyzed_and_downloaded_tracks['u'] > 0:
                            messagebox.showinfo('Инфо',
                                                f'Добавление в базу данных треков плейлиста [{current_playlist.title}]'
                                                f' закончено!\n'
                                                f'Добавлено [{self.downloading_or_updating_playlists[playlist.kind].analyzed_and_downloaded_tracks["u"]}] трека(ов).\n'
                                                f'Не удалось добавить [{self.downloading_or_updating_playlists[playlist.kind].analyzed_and_downloaded_tracks["e"]}] трека(ов).')
                        else:
                            messagebox.showinfo('Инфо',
                                                f'В выбранной базе данных [{self.history_database_path}] уже '
                                                f'присутствуют все треки из плейлиста [{current_playlist.title}].')
                    else:
                        if self.downloading_or_updating_playlists[playlist.kind]. \
                                analyzed_and_downloaded_tracks['d'] > 0:
                            messagebox.showinfo('Инфо',
                                                f'Загрузка треков плейлиста [{current_playlist.title}] закончена!\n'
                                                f'Загружено [{self.downloading_or_updating_playlists[playlist.kind].analyzed_and_downloaded_tracks["d"]}] трека(ов).\n'
                                                f'Не удалось загрузить [{self.downloading_or_updating_playlists[playlist.kind].analyzed_and_downloaded_tracks["e"]}] трека(ов).')
                        else:
                            messagebox.showinfo('Инфо', f'В плейлисте [{current_playlist.title}] нет новых треков!\n\n'
                                                        f'Если хотите скачать треки, то уберите галочку с пункта '
                                                        f'"Скачать новые треки".\n'
                                                        f'Если хотите, чтобы существующие треки были перезаписаны, '
                                                        f'то поставьте соответствующую галочку в окне конфигурации '
                                                        f'или в меню "Дополнительно".')
            except IOError:
                messagebox.showwarning('Предупреждение', f'Не удалось создать файл [{filename}] для записи ошибок при '
                                                         f'скачивании!')
                logger.error(f'Ошибка при попытке создания файла [{filename}] для записи ошибок при скачивании!')

            info = "скачиваемых" if (not update_mode and not only_add_to_database) else "обновляемых"
            try:
                del self.downloading_or_updating_playlists[playlist.kind]
                logger.debug(f'Плейлист [{playlist_title}] был удалён из списка {info} плейлистов.')
            except ValueError:
                logger.error(f'Не удалось удалить плейлист [{playlist_title}] из списка {info} плейлистов.')

        except NetworkError:
            logger.error('Возникла ошибка с подключением к Яндекс Музыке, завершаю работу...')
            messagebox.showerror('Ошибка', 'Возникла ошибка с подключением к Яндекс Музыке!\nПопробуйте позже.')
            child_window.destroy()

        except Exception:
            logger.exception('')
            pass

    def _database_create_tables(self):
        """
        Создаем необходмые таблицы в базе данных, если их ещё нет
        :return:
        """
        with sqlite3.connect(self.history_database_path) as db:
            logger.debug(f'База данных по пути [{self.history_database_path}] была открыта.')
            for playlist in self.playlists:
                playlist_title = strip_bad_symbols(playlist.title).replace(' ', '_')
                cur = db.cursor()
                request = f"CREATE TABLE IF NOT EXISTS table_{playlist_title}(" \
                          f"track_id INTEGER NOT NULL," \
                          f"artist_id TEXT NOT NULL," \
                          f"album_id TEXT," \
                          f"track_name TEXT NOT NULL," \
                          f"artist_name TEXT NOT NULL," \
                          f"album_name TEXT," \
                          f"genre TEXT," \
                          f"track_number INTEGER NOT NULL," \
                          f"disk_number INTEGER NOT NULL," \
                          f"year INTEGER," \
                          f"release_data TEXT," \
                          f"bit_rate INTEGER NOT NULL," \
                          f"codec TEXT NOT NULL," \
                          f"is_favorite INTEGER NOT NULL," \
                          f"is_explicit INTEGER NOT NULL DEFAULT 0," \
                          f"is_popular INTEGER NOT NULL DEFAULT 0" \
                          f")"
                cur.execute(request)

    class DownloaderHelper:
        def __init__(self, progress_bar: Progressbar, label_value: tkinter.Label, download_folder_path: str,
                     history_database_path: str, is_rewritable: bool, download_only_new: bool, filenames: dict,
                     playlist_title: str, number_tracks_in_playlist: int, liked_tracks: TracksList,
                     add_track_id_to_name: bool, main_thread_state, child_thread_state, update_mode,
                     only_add_to_database):
            self.progress_bar = progress_bar
            self.label_value = label_value
            self.download_folder_path = download_folder_path
            self.history_database_path = history_database_path
            self.is_rewritable = is_rewritable
            self.download_only_new = download_only_new
            self.filenames = filenames
            self.playlist_title = playlist_title
            self.number_tracks_in_playlist = number_tracks_in_playlist
            self.liked_tracks = liked_tracks
            self.add_track_id_to_name = add_track_id_to_name
            self.main_thread_state = main_thread_state
            self.child_thread_state = child_thread_state
            self.update_mode = update_mode
            self.only_add_to_database = only_add_to_database

            self.is_downloading_finished = False
            self.mutex = threading.Lock()
            self.analyzed_and_downloaded_tracks = {'a': 0, 'd': 0, 'u': 0, 'e': 0}

        def change_progress_bar_state(self, download_state: str = ''):
            """
            Изменяем состояние прогрессбара
            :param download_state:
            :return:
            """
            self.mutex.acquire()
            text = self.label_value['text'].split('(')[0].split(':')[0]
            track_downloaded_digital = f'{self.analyzed_and_downloaded_tracks["a"]}/{self.number_tracks_in_playlist}'
            track_downloaded_percentage = "{:0.2f} %".format(
                self.analyzed_and_downloaded_tracks["a"] / self.number_tracks_in_playlist * 100)

            self.label_value.config(
                text=f'{text}: {track_downloaded_digital} [{track_downloaded_percentage}]{download_state}')
            self.progress_bar['value'] = self.analyzed_and_downloaded_tracks["a"] / self.number_tracks_in_playlist * 100
            self.mutex.release()
            logger.debug(f'Значения прогресс бара для плейлиста [{self.playlist_title}] были изменены.')

        def _is_track_liked(self, track_id) -> bool:
            """
            Проверяем, находится ли трек в списке любимых
            :param track_id: идентификатор трека
            :return:
            """
            for track in self.liked_tracks:
                if track_id == track.id:
                    return True
            return False

        def download_track(self, track: Track):
            """
            Скачивает полученный трек, параллельно добавляя о нём всю доступную информацию в базу данных.
            :param track: текущий трек
            :return:
            """
            try:
                track_artists = ', '.join(i['name'] for i in track.artists)
                track_title = track.title + ("" if track.version is None else f' ({track.version})')
                track_id = ''
                if self.add_track_id_to_name:
                    track_id = f' [{track.id}]'
                track_name = strip_bad_symbols(f"{track_artists} - {track_title}{track_id}", soft_mode=True)

                if not self.main_thread_state() or not self.child_thread_state():
                    logger.debug('Основное окно или окно загрузки получило сигнал на завершение, начинаю подготовку '
                                 'к прекращению работы.')
                    return

                if self.download_only_new:
                    # self.mutex.acquire()
                    return_value = self._is_track_in_database(track=track)
                    # self.mutex.release()

                    if return_value:
                        logger.debug(f'Трек [{track_name}] уже существует в базе '
                                     f'[{self.history_database_path}]. Так как включён мод ONLY_NEW, выхожу.')
                        return
                    else:
                        logger.debug(f'Трека [{track_name}] нет в базе '
                                     f'[{self.history_database_path}]. Подготавливаюсь к его загрузки.')

                if not track.available:
                    logger.error(f'Трек [{track_name}] недоступен.')
                    # self.mutex.acquire()
                    with open(self.filenames['e'], 'a', encoding='utf-8') as file:
                        file.write(f"{track_name} ~ Трек недоступен\n")
                    self.analyzed_and_downloaded_tracks["e"] += 1
                    # self.mutex.release()
                    return

                was_track_downloaded = False
                track_exists = False
                for info in sorted(track.get_download_info(), key=lambda x: x['bitrate_in_kbps'], reverse=True):
                    codec = info.codec
                    bitrate = info.bitrate_in_kbps
                    full_track_name = os.path.abspath(f'{self.download_folder_path}/{track_name}.{codec}')

                    # Если трек существует и мы не перезаписываем, то выходим, но скачала проеверяем, есть ли он в базе
                    if os.path.exists(f'{full_track_name}') and not self.is_rewritable:
                        if not self.main_thread_state() or not self.child_thread_state():
                            logger.debug('Основное окно или окно загрузки получило сигнал на завершение, '
                                         'начинаю подготовку к прекращению работы.')
                            return

                        logger.debug(f'Трек [{track_name}] уже существует на диске '
                                     f'[{self.download_folder_path}]. Проверяю в базе.')
                        # self.mutex.acquire()
                        if self._is_track_in_database(track):
                            logger.debug(f'Трек [{track_name}] уже существует в базе '
                                         f'[{self.history_database_path}]. Так как отключена перезапись, выхожу.')
                        else:
                            logger.debug(f'Трек [{track_name}] отсутствует в базе '
                                         f'[{self.history_database_path}]. Так как отключена перезапись, просто '
                                         f'добавляю его в базу и выхожу.')
                            self._add_track_to_database(track=track, codec=codec, bit_rate=bitrate,
                                                        is_favorite=self._is_track_liked(track.id))
                            logger.debug(
                                f'Трек [{track_name}] был добавлен в базу данных [{self.history_database_path}].')

                        # with open(self.filenames['e'], 'a', encoding='utf-8') as file:
                        #     file.write(f"{track_name} - Трек уже существует\n")
                        # self.mutex.release()
                        track_exists = True
                        break

                    try:
                        if not self.main_thread_state() or not self.child_thread_state():
                            logger.debug('Основное окно или окно загрузки получило сигнал на завершение, '
                                         'начинаю подготовку к прекращению работы.')
                            return

                        logger.debug(f'Начинаю загрузку трека [{track_name}].')
                        track.download(filename=full_track_name, codec=codec, bitrate_in_kbps=bitrate)
                        logger.debug(f'Трек [{track_name}] был скачан.')

                        self.mutex.acquire()
                        with open(f'{self.filenames["d"]}', 'a', encoding='utf-8') as file:
                            file.write(f'{self.analyzed_and_downloaded_tracks["d"]}] {track_name}\n')
                        self.mutex.release()

                        cover_filename = os.path.abspath(f'{self.download_folder_path}/covers/{track_name}.jpg')
                        track.download_cover(cover_filename, size="300x300")
                        logger.debug(f'Обложка для трека [{track_name}] была скачана в [{cover_filename}].')

                        try:
                            lyrics = track.get_supplement().lyrics
                            self._write_track_metadata(full_track_name=full_track_name,
                                                       track_title=track_title,
                                                       artists=track.artists,
                                                       albums=track.albums,
                                                       genre=track.albums[0].genre,
                                                       album_artists=track.albums[0].artists,
                                                       year=track.albums[0]['year'],
                                                       cover_filename=cover_filename,
                                                       track_position=track.albums[0].track_position.index,
                                                       disk_number=track.albums[0].track_position.volume,
                                                       lyrics=lyrics)
                            logger.debug(f'Метаданные трека [{track_name}] были обновлены.')
                        except AttributeError:
                            logger.error(f'Не удалось обновить метаданные для файла [{full_track_name}].')
                        except TypeError:
                            logger.error(f'Не удалось обновить метаданные для файла [{full_track_name}].')

                        # self.mutex.acquire()
                        if not self._is_track_in_database(track=track):
                            logger.debug(f'Трек [{track_name}] отсутствует в базе данных по пути '
                                         f'[{self.history_database_path}]. Добавляю в базу.')
                            self._add_track_to_database(track=track, codec=codec, bit_rate=bitrate,
                                                        is_favorite=self._is_track_liked(track.id))
                            logger.debug(
                                f'Трек [{track_name}] был добавлен в базу данных [{self.history_database_path}].')
                        else:
                            logger.debug(f'Трек [{track_name}] уже присутствует в базе данных по пути '
                                         f'[{self.history_database_path}].')

                        self.mutex.acquire()
                        self.analyzed_and_downloaded_tracks["d"] += 1
                        self.mutex.release()
                        was_track_downloaded = True
                        break
                    except (YandexMusicError, TimeoutError):
                        continue

                if not was_track_downloaded:
                    if not track_exists:
                        logger.error(f'Не удалось скачать трек [{track_name}].')
                        # self.mutex.acquire()
                        with open(self.filenames['e'], 'a', encoding='utf-8') as file:
                            file.write(f"{track_name} ~ Не удалось скачать трек\n")
                        self.analyzed_and_downloaded_tracks["e"] += 1
                        # self.mutex.release()

            except IOError:
                logger.error(f'Ошибка при попытке записи в один из файлов [{self.filenames["e"]}] или '
                             f'[{self.filenames["d"]}].')
                self.analyzed_and_downloaded_tracks["e"] += 1

            finally:
                # self.mutex.acquire()
                self.analyzed_and_downloaded_tracks["a"] += 1
                # self.mutex.release()

        def _is_track_in_database(self, track: Track) -> bool:
            """
            Ищет трек в базе данных
            :param track: трек
            :return: True - если нашел, False - если нет.
            """
            _playlist_name = self.playlist_title.replace(' ', '_')
            _playlist_name = f'table_{_playlist_name}'

            track_artists = ', '.join(i['name'] for i in track.artists)
            track_title = track.title + ("" if track.version is None else f' ({track.version})')
            track_id = ''
            if self.add_track_id_to_name:
                track_id = f' [{track.id}]'
            track_name = strip_bad_symbols(f"{track_artists} - {track_title}{track_id}", soft_mode=True)
            logger.debug(f'Ищу трек [{track_name}] в базе [{self.history_database_path}].')

            try:
                with sqlite3.connect(self.history_database_path) as con:
                    cursor = con.cursor()
                    request = f"SELECT * FROM {_playlist_name} WHERE track_id == ? " \
                              f"OR (track_name == ? " \
                              f"AND artist_name == ?);"
                    result = cursor.execute(request, [track.id, track_title, track_artists])
                    return True if result.fetchone() else False
            except Exception:
                logger.error('Вылет в проверке!')
                return True

        def _add_track_to_database(self, track: Track, codec: str, bit_rate: int, is_favorite: int):
            """
            Добавляет трек в базу данных
            :param track: трек
            :param codec: кодек трека
            :param bit_rate: битрейт трека
            :param is_favorite: есть ли трек в списке любимых
            :return:
            """
            _playlist_name = self.playlist_title.replace(' ', '_')
            _playlist_name = f'table_{_playlist_name}'

            track_artists = ', '.join(i['name'] for i in track.artists)
            track_title = track.title + ("" if track.version is None else f' ({track.version})')
            track_id = ''
            if self.add_track_id_to_name:
                track_id = f' [{track.id}]'
            track_name = strip_bad_symbols(f"{track_artists} - {track_title}{track_id}", soft_mode=True)
            logger.debug(f'Добавляю трек [{track_name}] в базу [{self.history_database_path}].')

            con = None
            metadata = []
            try:
                con = sqlite3.connect(self.history_database_path)
                cursor = con.cursor()
                request = f"INSERT INTO {_playlist_name}(" \
                          f"track_id, artist_id, album_id, track_name, artist_name, album_name, genre, track_number, " \
                          f"disk_number, year, release_data, bit_rate, codec, is_favorite, is_explicit, is_popular) " \
                          f"VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);"

                track_id = int(track.id)
                artist_id = ', '.join(str(i.id) for i in track.artists)
                album_id = ', '.join(str(i.id) for i in track.albums)
                track_name = track_title
                artist_name = track_artists
                album_name = ', '.join(i.title for i in track.albums)
                genre = track.albums[0].genre
                track_number = track.albums[0].track_position.index
                disk_number = track.albums[0].track_position.volume
                year = track.albums[0].year
                release_data = track.albums[0].release_date
                is_explicit = True if track.content_warning is not None else False
                is_popular = True if int(track.id) in track.albums[0].bests else False

                metadata = [track_id, artist_id, album_id, track_name, artist_name, album_name,
                            genre, track_number, disk_number, year, release_data, bit_rate, codec,
                            is_favorite, is_explicit, is_popular]

                cursor.execute(request, metadata)
                con.commit()

            except sqlite3.Error:
                messagebox.showerror('Ошибка', 'Не удалось выполнить SQL запрос вставки!')
                logger.error(f'Не удалось выполнить SQL запрос вставки. Данные: [{metadata}].')
                if con is not None:
                    con.rollback()
            finally:
                if con is not None:
                    con.close()

        @staticmethod
        def _write_track_metadata(full_track_name, track_title, artists, albums, genre, album_artists, year,
                                  cover_filename, track_position, disk_number, lyrics):
            """
            Функция для редактирования метаданных трека
            :param full_track_name: путь к треку
            :param track_title: название трека
            :param artists: исполнители
            :param albums: альбомы
            :param genre: жанр
            :param album_artists: исполнители альбома
            :param year: год
            :param cover_filename: путь к обложке
            :param track_position: номер трека в альбоме
            :param disk_number: номер диска (если есть)
            :param lyrics: текст песни (если есть)
            :return:
            """
            file = File(full_track_name)
            with open(cover_filename, 'rb') as cover_file:
                file.update({
                    # Title
                    'TIT2': TIT2(encoding=3, text=track_title),
                    # Artist
                    'TPE1': TPE1(encoding=3, text=', '.join(i['name'] for i in artists)),
                    # Album
                    'TALB': TALB(encoding=3, text=', '.join(i['title'] for i in albums)),
                    # Genre
                    'TCON': TCON(encoding=3, text=genre),
                    # Album artists
                    'TPE2': TPE2(encoding=3, text=', '.join(i['name'] for i in album_artists)),
                    # Year
                    'TDRC': TDRC(encoding=3, text=str(year)),
                    # Picture
                    'APIC': APIC(encoding=3, text=cover_filename, data=cover_file.read()),
                    # Track number
                    'TRCK': TRCK(encoding=3, text=str(track_position)),
                    # Disk number
                    'TPOS': TPOS(encoding=3, text=str(disk_number))
                })
            if lyrics is not None:
                # Song lyrics
                file.tags.add(USLT(encoding=3, text=lyrics.full_lyrics))
            file.save()

        def add_track_to_database(self, track: Track):
            """
            Добавляет текущий трек в базу данных, если его там нет
            :param track: текущий трек
            :return:
            """
            track_artists = ', '.join(i['name'] for i in track.artists)
            track_title = track.title + ("" if track.version is None else f' ({track.version})')
            track_id = ''
            if self.add_track_id_to_name:
                track_id = f' [{track.id}]'
            track_name = strip_bad_symbols(f"{track_artists} - {track_title}{track_id}", soft_mode=True)

            if not track.available:
                logger.error(f'Трек [{track_name}] недоступен!')
                # self.mutex.acquire()
                self.analyzed_and_downloaded_tracks["a"] += 1
                self.analyzed_and_downloaded_tracks["e"] += 1
                # self.mutex.release()
                return

            # self.mutex.acquire()
            result = self._is_track_in_database(track)
            # self.mutex.release()

            if not result:
                info = sorted(track.get_download_info(), key=lambda x: x['bitrate_in_kbps'], reverse=True)[0]
                codec = info.codec
                bitrate = info.bitrate_in_kbps

                logger.debug(f'Трек [{track_name}] отсутствует в базе [{self.history_database_path}].')
                # self.mutex.acquire()
                self._add_track_to_database(track=track, codec=codec, bit_rate=bitrate,
                                            is_favorite=self._is_track_liked(track.id))
                self.analyzed_and_downloaded_tracks["u"] += 1
                # self.mutex.release()
                logger.debug(f'Трек [{track_name}] был добавлен в базу данных [{self.history_database_path}].')
            else:
                logger.debug(f'Трек [{track_name}] уже существует в базе [{self.history_database_path}].')

            # self.mutex.acquire()
            self.analyzed_and_downloaded_tracks["a"] += 1
            # self.mutex.release()

        def update_track_metadata(self, track: Track):
            """
            Обновляет метаданные трека
            :param track: текущий трек
            :return:
            """
            track_artists = ', '.join(i['name'] for i in track.artists)
            track_title = track.title + ("" if track.version is None else f' ({track.version})')
            track_id = ''
            if self.add_track_id_to_name:
                track_id = f' [{track.id}]'
            track_name = strip_bad_symbols(f"{track_artists} - {track_title}{track_id}", soft_mode=True)

            if not self.main_thread_state() or not self.child_thread_state():
                logger.debug('Основное окно или окно загрузки получило сигнал на завершение, начинаю подготовку '
                             'к прекращению работы.')
                return

            if not track.available:
                logger.error(f'Трек [{track_name}] недоступен.')
                self.analyzed_and_downloaded_tracks["a"] += 1
                self.analyzed_and_downloaded_tracks["e"] += 1
                return

            for info in sorted(track.get_download_info(), key=lambda x: x['bitrate_in_kbps'], reverse=True):
                codec = info.codec
                full_track_name = os.path.abspath(f'{self.download_folder_path}/{track_name}.{codec}')

                # Если трек существует и мы не перезаписываем, то выходим, но скачала проеверяем, есть ли он в базе
                if os.path.exists(f'{full_track_name}'):
                    logger.debug(f'Трек [{track_name}] присутствует на диске '
                                 f'[{self.download_folder_path}]. Пытаюсь обновить метаданные.')

                    cover_filename = os.path.abspath(f'{self.download_folder_path}/covers/{track_name}.jpg')
                    if not os.path.exists(cover_filename):
                        logger.debug(f'Обложка для трека [{track_name}] не найдена, начинаю загрузку.')
                        track.download_cover(cover_filename, size="300x300")
                        logger.debug(f'Обложка для трека [{track_name}] была скачана в [{cover_filename}].')
                    try:
                        lyrics = track.get_supplement().lyrics
                        self._write_track_metadata(full_track_name=full_track_name,
                                                   track_title=track_title,
                                                   artists=track.artists,
                                                   albums=track.albums,
                                                   genre=track.albums[0].genre,
                                                   album_artists=track.albums[0].artists,
                                                   year=track.albums[0]['year'],
                                                   cover_filename=cover_filename,
                                                   track_position=track.albums[0].track_position.index,
                                                   disk_number=track.albums[0].track_position.volume,
                                                   lyrics=lyrics)
                        logger.debug(f'Метаданные трека [{track_name}] были обновлены.')
                    except AttributeError:
                        logger.error(f'Не удалось обновить метаданные для файла [{full_track_name}].')
                    except TypeError:
                        logger.error(f'Не удалось обновить метаданные для файла [{full_track_name}].')

                    self.analyzed_and_downloaded_tracks['u'] += 1
                    break
            self.analyzed_and_downloaded_tracks['a'] += 1

        def _update_track_name(self, track: Track):
            """
            Изменяет названия треков, как в базе данных, так и в проводнике
            :param track: трек
            :return:
            """
            track_artists = ', '.join(i['name'] for i in track.artists)
            track_title = track.title + ("" if track.version is None else f' ({track.version})')
            track_id = ''
            if self.add_track_id_to_name:
                track_id = f' [{track.id}]'
            track_name = f"{track_artists} - {track_title}{track_id}"
            old_track_name = strip_bad_symbols(f"{track_name}")
            new_track_name = strip_bad_symbols(f"{track_name}", soft_mode=True)

            if os.path.exists(f'{self.download_folder_path}/{old_track_name}.mp3'):
                try:
                    os.rename(f'{self.download_folder_path}/{old_track_name}.mp3',
                              f'{self.download_folder_path}/{new_track_name}.mp3')
                    logger.debug(f'Файл был успешно переименован из [{old_track_name}] в [{new_track_name}].')
                    self.mutex.acquire()
                    self.analyzed_and_downloaded_tracks['a'] += 1
                    self.mutex.release()
                except Exception:
                    logger.error(f'Не удалось переименовать файл [{old_track_name}] в [{new_track_name}].')

    class DownloaderWorker(threading.Thread):
        is_network_error = False
        _network_error_was_showed = False

        def __init__(self, queue: Queue, helper):
            threading.Thread.__init__(self)
            self.queue = queue
            self.helper = helper
            self.is_finished = False

        def run(self):
            while True:
                if self.is_finished:
                    logger.debug('Выхожу из цикла обработки')
                    break

                try:
                    track = self.queue.get(block=False)
                    logger.debug('Получил данные из очереди.')
                except Empty:
                    continue

                try:
                    if not self.helper.main_thread_state() or not self.helper.child_thread_state() or self.is_finished:
                        break

                    track_artists = ', '.join(i['name'] for i in track.artists)
                    track_title = track.title + ("" if track.version is None else f' ({track.version})')
                    track_id = ''
                    if self.helper.add_track_id_to_name:
                        track_id = f' [{track.id}]'
                    track_name = strip_bad_symbols(f"{track_artists} - {track_title}{track_id}", soft_mode=True)

                    # logger.debug(f'Подготовка к началу обновления трека [{track_name}].')
                    # self.helper._update_track_name(track)
                    # logger.debug(f'Обновление трека [{track_name}] завершено.')

                    if self.helper.update_mode:
                        logger.debug(f'Подготовка к началу обновления трека [{track_name}].')
                        self.helper.update_track_metadata(track)
                        logger.debug(f'Обновление трека [{track_name}] завершено.')
                    elif self.helper.only_add_to_database:
                        logger.debug(f'Подготовка к началу добавления трека [{track_name}] в базу данных '
                                     f'[{self.helper.history_database_path}].')
                        self.helper.add_track_to_database(track)
                        logger.debug(f'Добавление трека [{track_name}] в базу данных '
                                     f'[{self.helper.history_database_path}] завершено.')
                    else:
                        logger.debug(f'Подготовка к началу загрузки трека [{track_name}].')
                        self.helper.download_track(track)
                        logger.debug(f'Загрузка трека [{track_name}] завершена.')

                    if not self.helper.main_thread_state() or not self.helper.child_thread_state() or self.is_finished:
                        break

                    self.helper.change_progress_bar_state()
                    logger.debug(f'Програсс бар с учётом трека [{track_name}] изменён.')

                except NetworkError:
                    logger.error('Не удалось связаться с сервисом Яндекс Музыка!')
                    if not YandexMusicDownloader.DownloaderWorker._network_error_was_showed:
                        YandexMusicDownloader.DownloaderWorker._network_error_was_showed = True
                        messagebox.showerror('Ошибка', 'Не удалось связаться с сервисом Яндекс Музыка!'
                                                       '\nПопробуйте позже.')
                        YandexMusicDownloader.DownloaderWorker.is_network_error = True
                    break

                except Exception:
                    logger.error('Что-то пошло не так.')

                finally:
                    self.queue.task_done()

            logger.debug(f'Начинаю отчищать очередь. Текущий размер очереди {self.queue.qsize()}.')
            while not self.queue.empty():
                self.queue.get()
                self.queue.task_done()

            logger.debug(f'Отчистил очередь. Текущий размер очереди {self.queue.qsize()}. '
                         f'Количество невыполненных заданий {self.queue.unfinished_tasks}.')


def main():
    setup_logger(logging.ERROR)
    downloader = YandexMusicDownloader()
    downloader.start()


if __name__ == '__main__':
    main()
