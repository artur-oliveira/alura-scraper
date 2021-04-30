import pickle
from decouple import config
from json import JSONDecodeError
from requests import Session
from bs4 import BeautifulSoup
from typing import List, Dict, Any

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
    def __init__(self: 'AluraScraper', username: str, password: str, category: str) -> None:
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
        if self.file_exists('cookie.pickle'):
            self.browser.cookies = self.load_cookies()
            self.signed_in = True
        else:
            self.browser.post(self.BASE_LOGIN_URL, data={'username': self.username, 'password': self.password})
            self.signed_in = True
            self.save_cookies()

        return self

    def get_courses(self: 'AluraScraper') -> 'AluraScraper':
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
        data: dict = self.__download_m3u8_playlists(self.__get_download_links(course))

        for key in data.keys():
            for i in range(len(data.get(key))):
                self.download(data.get(key)[i], '%d-%d.ts' % (key, i))

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

    def __download_m3u8_playlists(self, list_links: List[str]) -> dict:
        filename: str = 'index.m3u8'
        list_links_return: dict = {}
        count: int = 1
        for link in list_links:
            self.download(link, filename)

            with open(filename, 'r') as playlist:
                list_links_return[count] = ['https://video.alura.com.br' + line.strip() for line in playlist
                                            if line.strip().startswith('/hls/alura/')]

            count += 1

        return list_links_return

    def download(self, link, filename):
        with self.browser.get(link) as res:
            with open(filename, 'wb') as f:
                for chunk in res.iter_content(chunk_size=8192):
                    f.write(chunk)

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


class Menu:
    def __init__(self: 'Menu'):
        self.scraper: 'AluraScraper'

    def show_menu(self: 'Menu') -> None:
        course = self.__choose_course()
        self.scraper.download_videos_course(course)

    def __choose_category(self: 'Menu') -> List[Dict]:
        self.scraper = AluraScraper(CREDENTIALS.get('username'),
                                    CREDENTIALS.get('password'),
                                    self.__choose_valid_option_or_exit(CATEGORIES)).login().get_courses()
        return self.scraper.course_by_subcategory

    def __choose_subcategory(self: 'Menu') -> List[Dict]:
        return self.__choose_valid_option_or_exit(self.__choose_category())

    def __choose_course(self: 'Menu') -> str:
        return self.__choose_valid_option_or_exit(self.__choose_subcategory())

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
