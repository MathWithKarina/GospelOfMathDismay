from __future__ import annotations
import locale, os, json
from pathlib import Path
SUPPORTED_LANGUAGES={"ru":"Русский","en-GB":"English (UK)"}
RU={
"app.title":"Gospel Of Math Dismay","nav.studio":"Студия","nav.projects":"Проекты и сцены","nav.models":"Каталог голосов","nav.media":"Медиатека","nav.graphs":"Графики","nav.analyzer":"Анализ аудио","nav.vocal":"Vocal α","nav.pronunciation":"Словарь произношения","nav.settings":"Настройки и справка",
"studio.source":"Исходный текст","studio.normalized":"Текст для озвучивания","studio.normalize":"Нормализовать математику","studio.synthesize":"Синтезировать WAV","studio.preview":"Прослушать WAV","studio.save":"Сохранить сцену","studio.engine":"Движок","studio.model":"Голосовая модель","studio.text_language":"Язык текста","studio.status":"Готово","studio.project":"Проект","studio.no_project":"Проект не выбран — WAV можно сохранить отдельно.",
"project.new":"Новый проект","project.open":"Открыть проект","project.add":"Добавить сцену","project.duplicate":"Дублировать","project.delete":"Удалить сцену","project.up":"Выше","project.down":"Ниже","project.save":"Сохранить проект","project.batch":"Пакетный синтез","project.assemble":"Собрать final.wav","project.name":"Название проекта","project.scenes":"Сцены","project.select":"Выберите сцену","project.empty":"Создайте или откройте проект, чтобы управлять сценами.",
"models.search":"Найти голоса онлайн","models.language":"Язык","models.query":"Поиск по названию","models.download":"Скачать выбранную модель","models.refresh":"Обновить каталог","models.note":"Каталог загружается с Hugging Face. У моделей разные лицензии — читайте карточку до коммерческого использования.","models.installed":"Установлена","models.not_installed":"Не установлена",
"media.choose":"Выбрать папку","media.scan":"Обновить","media.play":"Прослушать","media.rename":"Переименовать","media.move":"Переместить","media.delete":"Удалить","media.add_project":"Добавить в проект","media.query":"Поиск аудио","media.empty":"Выберите папку, чтобы просмотреть WAV-файлы.",
"graphs.expression":"Функция (например, y=x^2)","graphs.xmin":"X от","graphs.xmax":"X до","graphs.ymin":"Y от","graphs.ymax":"Y до","graphs.render":"Построить и экспортировать","graphs.csv":"Экспорт CSV","graphs.file":"Выходной файл","graphs.error":"Не удалось построить график",
"audio.open":"Открыть WAV","audio.export":"Экспорт анализа в CSV","audio.save_image":"Сохранить изображение","audio.spectrogram":"Спектрограмма","audio.waveform":"Осциллограмма","audio.spectrum":"Спектр","audio.duration":"Длительность","audio.rate":"Частота дискретизации","audio.channels":"Каналы","audio.peak":"Пик","audio.rms":"RMS",
"vocal.notice":"Я не уверена, что буду развивать это дальше","vocal.warning":"Экспериментальный piano roll: прослушивание создаёт простые синусоидальные тоны, а не естественный вокал.","vocal.add":"Добавить ноту","vocal.remove":"Удалить ноту","vocal.play":"Создать WAV-превью","vocal.save":"Сохранить MIDI-подобный проект","vocal.open":"Открыть проект","vocal.bpm":"Темп (BPM)","vocal.syllable":"Слог / символ",
"dict.add":"Добавить правило","dict.edit":"Изменить правило","dict.remove":"Удалить правило","dict.import":"Импорт JSON/CSV","dict.export":"Экспорт JSON","dict.source":"Исходное написание","dict.replacement":"Произношение","dict.language":"Язык","dict.priority":"Приоритет","dict.apply":"Применить словарь",
"settings.language":"Язык интерфейса","settings.pauses":"Настроить паузы","settings.piper":"Путь к Piper","settings.model_dir":"Каталог моделей","settings.output_dir":"Каталог экспорта","settings.save":"Сохранить настройки","settings.help":"Справка и диагностика","help.title":"Справка и диагностика","help.copy_error":"Копировать описание ошибки","help.copy_info":"Копировать техническую информацию","help.open_log":"Открыть журнал","help.docs":"Открыть руководство",
"common.browse":"Обзор…","common.cancel":"Отмена","common.ok":"ОК","common.error":"Ошибка","common.warning":"Предупреждение","common.success":"Готово","common.select_file":"Выбрать файл","common.copy":"Копировать","common.yes":"Да","common.no":"Нет","common.working":"Выполняется…","common.not_available":"Недоступно","common.no_model":"Модель не выбрана","common.confirm_delete":"Подтвердите удаление","common.saved":"Сохранено.","common.failed":"Операция не выполнена: {error}","common.ready":"Готово"
}
EN={
"app.title":"Gospel Of Math Dismay","nav.studio":"Studio","nav.projects":"Projects & scenes","nav.models":"Voice catalogue","nav.media":"Media library","nav.graphs":"Graphs","nav.analyzer":"Audio analysis","nav.vocal":"Vocal α","nav.pronunciation":"Pronunciation dictionary","nav.settings":"Settings & help",
"studio.source":"Source text","studio.normalized":"Speech-ready text","studio.normalize":"Normalize mathematics","studio.synthesize":"Synthesize WAV","studio.preview":"Play WAV","studio.save":"Save scene","studio.engine":"Engine","studio.model":"Voice model","studio.text_language":"Text language","studio.status":"Ready","studio.project":"Project","studio.no_project":"No project selected — you can save a WAV separately.",
"project.new":"New project","project.open":"Open project","project.add":"Add scene","project.duplicate":"Duplicate","project.delete":"Delete scene","project.up":"Move up","project.down":"Move down","project.save":"Save project","project.batch":"Batch synthesis","project.assemble":"Assemble final.wav","project.name":"Project name","project.scenes":"Scenes","project.select":"Select a scene","project.empty":"Create or open a project to manage scenes.",
"models.search":"Search voices online","models.language":"Language","models.query":"Search by name","models.download":"Download selected model","models.refresh":"Refresh catalogue","models.note":"The catalogue is fetched from Hugging Face. Model licences vary; read each model card before commercial use.","models.installed":"Installed","models.not_installed":"Not installed",
"media.choose":"Choose folder","media.scan":"Refresh","media.play":"Play","media.rename":"Rename","media.move":"Move","media.delete":"Delete","media.add_project":"Add to project","media.query":"Search audio","media.empty":"Choose a folder to browse WAV files.",
"graphs.expression":"Function (e.g. y=x^2)","graphs.xmin":"X min","graphs.xmax":"X max","graphs.ymin":"Y min","graphs.ymax":"Y max","graphs.render":"Plot and export","graphs.csv":"Export CSV","graphs.file":"Output file","graphs.error":"Could not render graph",
"audio.open":"Open WAV","audio.export":"Export analysis CSV","audio.save_image":"Save image","audio.spectrogram":"Spectrogram","audio.waveform":"Waveform","audio.spectrum":"Spectrum","audio.duration":"Duration","audio.rate":"Sample rate","audio.channels":"Channels","audio.peak":"Peak","audio.rms":"RMS",
"vocal.notice":"I'm not sure I'll continue developing this","vocal.warning":"Experimental piano roll: preview playback produces simple sine tones, not natural singing.","vocal.add":"Add note","vocal.remove":"Remove note","vocal.play":"Render WAV preview","vocal.save":"Save MIDI-like project","vocal.open":"Open project","vocal.bpm":"Tempo (BPM)","vocal.syllable":"Syllable / symbol",
"dict.add":"Add rule","dict.edit":"Edit rule","dict.remove":"Remove rule","dict.import":"Import JSON/CSV","dict.export":"Export JSON","dict.source":"Written form","dict.replacement":"Pronunciation","dict.language":"Language","dict.priority":"Priority","dict.apply":"Apply dictionary",
"settings.language":"Interface language","settings.pauses":"Configure pauses","settings.piper":"Piper executable path","settings.model_dir":"Model directory","settings.output_dir":"Export directory","settings.save":"Save settings","settings.help":"Help & diagnostics","help.title":"Help & diagnostics","help.copy_error":"Copy error description","help.copy_info":"Copy technical information","help.open_log":"Open log","help.docs":"Open guide",
"common.browse":"Browse…","common.cancel":"Cancel","common.ok":"OK","common.error":"Error","common.warning":"Warning","common.success":"Done","common.select_file":"Choose file","common.copy":"Copy","common.yes":"Yes","common.no":"No","common.confirm_delete":"Confirm deletion","common.saved":"Saved.","common.failed":"Operation failed: {error}","common.ready":"Ready","common.working":"Working…","common.not_available":"Unavailable","common.no_model":"No model selected"
}
def _load_catalog(code, fallback):
    filename="en-GB.json" if code=="en-GB" else "ru.json"
    path=Path(__file__).resolve().parents[1]/"locales"/filename
    try:
        catalog=json.loads(path.read_text(encoding="utf-8"))
        return {**fallback, **{str(k):str(v) for k,v in catalog.items()}}
    except (OSError,ValueError,TypeError):
        return fallback

_TABLES={"ru":_load_catalog("ru",RU),"en-GB":_load_catalog("en-GB",EN)}
def detect_windows_language() -> str:
    value=os.environ.get("LANG","")
    try: value=value or locale.getlocale()[0] or ""
    except (ValueError,TypeError): pass
    try:
        import ctypes
        if os.name=="nt":
            langid=ctypes.windll.kernel32.GetUserDefaultUILanguage()
            primary=langid & 0x3ff
            if primary==0x09: return "en-GB"
            if primary==0x19: return "ru"
    except Exception: pass
    return "en-GB" if value.lower().startswith(("en_gb","en-gb","en")) else "ru"
def translate(key: str, language: str="ru", **kwargs) -> str:
    text=_TABLES.get(language,EN).get(key) or EN.get(key) or RU.get(key) or key
    try: return text.format(**kwargs)
    except (KeyError,ValueError): return text
