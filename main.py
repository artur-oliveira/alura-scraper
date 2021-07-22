import os
import pickle
import shutil
from concurrent.futures import ThreadPoolExecutor

from decouple import config
from json import JSONDecodeError
from requests import Session
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from timeit import default_timer as timer

CREDENTIALS: Dict = {
    'username': config('EMAIL'),
    'password': config('PASSWORD')
}

CATEGORIES: List[Dict] = [{'Cursos Mobile': 'mobile'},
                          {'Cursos Programação': 'programacao'},
                          {'Cursos Front-end': 'front-end'},
                          {'Cursos Desing & UX': 'design-ux'},
                          {'Cursos DevOps': 'devops'},
                          {'Cursos Data Science': 'data-science'},
                          {'Cursos Inovação & Gestão': 'inovacao-gestao'}]


class AluraScraper(object):
    """
    Classe responsável por pegar todos os dados da Alura
    """
    def __init__(self: 'AluraScraper', username: str, password: str, category: str) -> None:
        """

        :param username: Nome do usuário
        :param password: Senha do usuário
        :param category: Categoria escolhida via menu
        """
        self.username: str = username
        self.password: str = password

        self.browser: Session = Session()
        self.BASE_URL: str = 'https://cursos.alura.com.br'
        self.BASE_LOGIN_URL: str = self.BASE_URL + '/signin'
        self.CATEGORY_URL: str = self.BASE_URL + '/category/' + category
        self.signed_in: bool = False

        self.course_by_subcategory: List[Dict[str: str]] = []
        self.course_data: List[Dict[str: str]] = []

    def login(self: 'AluraScraper') -> 'AluraScraper':
        """
        Realiza o login no site da alura, salva a sessão para que não precise ser feito o login novamente em algumas horas
        :return:
        """
        if self.file_exists('cookie.pickle'):
            self.browser.cookies = self.load_cookies()
            self.signed_in = True
        else:
            self.browser.post(self.BASE_LOGIN_URL, data={'username': self.username, 'password': self.password})
            self.signed_in = True
            self.save_cookies()

        return self

    def get_courses(self: 'AluraScraper') -> 'AluraScraper':
        """
        Pega todos os cursos disponíveis em uma determinada categoria
        :return:
        """
        assert self.is_logged()

        soup: BeautifulSoup = BeautifulSoup(self.browser.get(self.CATEGORY_URL).content, 'lxml')

        lista_nomes: List[str] = [str(it.text).strip() for it in soup.find_all(attrs={'id': 'subcategory__anchor'})]
        lista_tags: List[BeautifulSoup] = soup.find_all(attrs={'class': 'card-list category__card-list'})

        for i in range(len(lista_tags)):
            data_list = []
            li_tags: List[BeautifulSoup] = lista_tags[i].find_all('li')
            for li in li_tags:
                data_list.append({li.get('data-course-name'):
                                      li.find(attrs={'class': 'course-card__course-link'}).get('href')})

            self.course_by_subcategory.append({lista_nomes[i]: data_list})

        return self

    def download_videos_course(self: 'AluraScraper', course: str) -> None:
        """
        Faz o download de todos os vídeos de um determinado curso
        :param course: URL do curso que vai ser baixado
        :return:
        """
        name: str = course.split('/')[2]
        data: dict = self.__download_m3u8_playlists(self.__get_download_links(course))

        self.create_folder(name)

        tasks_ts_files: List[tuple] = []
        task_merge_files: List[tuple] = []

        for key in data.keys():
            video_folder: str = name + '/' + key
            task_merge_files.append((video_folder, ))

            self.create_folder(video_folder)
            for i in range(len(data.get(key))):
                tasks_ts_files.append((data.get(key)[i], '%s/%s-%d.ts' % (video_folder, key, i)))

        start = timer()
        print('COMEÇANDO O DOWNLOAD: %d PARTES ENCONTRADAS' % len(tasks_ts_files))
        self.execute_in_thread(tasks_ts_files, self.__download_ts_files)
        print('DOWNLOAD FINALIZADO EM %.2f SEGUNDOS' % (timer() - start))

        print('JUNTANDO TODOS OS VÍDEOS')
        self.execute_in_thread(task_merge_files, self.__merge_ts_files)

    def __download_ts_files(self: 'AluraScraper', task: List[tuple]) -> None:
        """
        Função que responsável para fazer o download dos arquivos TS (partes dos vídeos)
        :param task: Lista com tuplas que contém: O link, o nome do arquivo
        :return:
        """
        link, filename = task
        self.download(link, filename)

    def __merge_ts_files(self: 'AluraScraper', task: tuple) -> None:
        folder = task[0]
        onlyfiles = [f for f in os.listdir(folder) if f.endswith('.ts')]

        self.merge(folder, onlyfiles)

    @staticmethod
    def execute_in_thread(tasks: List[tuple], function, workers=8):
        """
        Função que executa uma função em multithreading
        :param tasks: Lista de tuplas
        :param function: função a ser executada
        :param workers: é como se fosse o número de threads 8 é suficiente, acima disso é praticamente perca de tempo
        :return:
        """
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pool.map(function, tasks)

    def __get_download_links(self: 'AluraScraper', course: str) -> List[str]:
        path: str = self.BASE_URL + course
        response = self.browser.get(self.BASE_URL +
                                    self.__get_task_link(BeautifulSoup(self.browser.get(path).content, 'lxml')))
        data = []
        count_vids: int = 1
        while 1:
            if response.url.endswith('#aulas'):
                break

            json_links = self.has_video_task(response.url)

            if json_links != '' and len(json_links) >= 1:
                data.append(json_links[0].get('link'))
                print('%d link(s) encontrado(s)' % count_vids)
                count_vids += 1

            response = self.browser.get(response.url + '/next')

        return data

    def __download_m3u8_playlists(self: 'AluraScraper', list_links: List[str]) -> dict:
        filename: str = 'index-%s.m3u8'
        list_links_return: dict = {}
        count: int = 1
        tasks: List[tuple] = []

        for link in list_links:
            tasks.append((link, filename % str(count), list_links_return))
            count += 1

        self.execute_in_thread(tasks, self.__download_m3u8)

        while len(tasks) > 0:
            tasks: List[tuple] = []
            for key in list_links_return.keys():
                if len(list_links_return.get(key)) == 0:
                    tasks.append((list_links[int(key) - 1], filename % key, list_links_return))

            self.execute_in_thread(tasks, self.__download_m3u8)

        return list_links_return

    def __download_m3u8(self, task: list) -> None:
        link, filename, list_links_return = task

        self.download(link, filename)

        with open(filename, 'r') as playlist:
            data = ['https://video.alura.com.br' + line.strip() for
                    line in playlist
                    if line.strip().startswith('/hls/alura/')]

        list_links_return[filename.split('-')[1].split('.')[0]] = data
        os.remove(filename)

    def download(self: 'AluraScraper', link: str, filename: str) -> None:
        with self.browser.get(link) as res:
            with open(filename, 'wb') as f:
                for chunk in res.iter_content(chunk_size=1024):
                    f.write(chunk)

    @staticmethod
    def merge(folder: str, data: List[str]) -> None:
        filename: str = folder.split('/')[0] + '/' + data[0].split('-')[0] + '.mp4'

        with open(filename, 'ab') as final:
            for item in data:
                with open(folder + '/' + item, 'rb') as temp:
                    final.write(temp.read())

        shutil.rmtree(folder)

    def is_logged(self: 'AluraScraper') -> bool:
        return self.signed_in

    def has_video_task(self: 'AluraScraper', url_task: str) -> Any:
        try:
            return self.browser.get(url_task + '/video').json() if url_task.startswith('https://') else \
                self.browser.get(self.BASE_URL + url_task + '/video').json()
        except JSONDecodeError:
            return ''

    @staticmethod
    def __get_task_link(soup: BeautifulSoup) -> str:
        return [item.get('href') for item in soup.find_all('a', attrs={'class': 'courseSectionList-section'})][0]

    def save_cookies(self: 'AluraScraper'):
        with open('cookie.pickle', 'wb') as f:
            pickle.dump(self.browser.cookies, f)

    @staticmethod
    def load_cookies():
        with open('cookie.pickle', 'rb') as f:
            return pickle.load(f)

    @staticmethod
    def file_exists(filename: str) -> bool:
        try:
            open(filename)
            return True
        except FileNotFoundError:
            return False

    @staticmethod
    def create_folder(folder: str) -> None:
        try:
            os.makedirs(folder)
            print('A PASTA %s FOI CRIADA' % folder)
        except FileExistsError:
            print('A PASTA %s JÁ EXISTE' % folder)


class Menu:
    def __init__(self: 'Menu'):
        self.scraper: 'AluraScraper'

    def show_menu(self: 'Menu') -> None:
        course = self.__choose_course()
        for item in course:
            self.scraper.download_videos_course(item)

    def __choose_category(self: 'Menu') -> List[Dict]:
        self.scraper = AluraScraper(CREDENTIALS.get('username'),
                                    CREDENTIALS.get('password'),
                                    self.__choose_valid_option_or_exit(CATEGORIES)).login().get_courses()
        return self.scraper.course_by_subcategory

    def __choose_subcategory(self: 'Menu') -> List[Dict]:
        return self.__choose_valid_option_or_exit(self.__choose_category())

    def __choose_course(self: 'Menu') -> List[str]:
        data = self.__choose_subcategory()
        return [list(data[i].values())[0] for i in range(len(data))]

    @staticmethod
    def __choose_valid_option_or_exit(data: List[Dict]) -> Any:
        print('Escolha uma das opções abaixo:')

        for i in range(len(data)):
            print('%d - %s' % ((i + 1), list(data[i].keys())[0]))
        print('0 - Sair\n')

        while 1:
            try:
                option = int(input('Opção: '))

                if option < 1:
                    break

                return list(data[option - 1].values())[0]

            except ValueError:
                print('Opção inválida\n')
            except IndexError:
                print('Escolha um dos valores da lista\n')

        exit(0)


if __name__ == '__main__':
    Menu().show_menu()
