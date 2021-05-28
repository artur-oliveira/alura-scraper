import os
from typing import List
import shutil

onlyfiles = [f for f in os.listdir('react-native-design-system/1') if f.endswith('.ts')]


print(sorted(onlyfiles, key=lambda x: int(x.split('.')[0].split('-')[1])))


def merge(folder: str, data: List[str]) -> None:
    folder_path = folder.split('/')[0]
    filename: str = folder + '/' + data[0].split('-')[0] + '.mp4'

    with open(filename, 'ab') as final:
        for item in data:
            with open(folder + '/' + item, 'rb') as temp:
                final.write(temp.read())


shutil.rmtree('react-native-design-system/1')