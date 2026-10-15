"""Original, user-supplied Boeun artwork shared by previews and documents."""
from app_paths import resource_dir


ARTWORK = {
    'symbol': dict(file='boeun-symbol.jpg', pixels=(541, 536),
                   alt='보은군 심벌마크', max_width=5600),
    'slogan': dict(file='vision-stacked.jpg', pixels=(3405, 1170),
                   alt='군민이 행복한 도시형 농촌 보은', max_width=14500),
    'vision-wide': dict(file='vision-wide.jpg', pixels=(3403, 741),
                        alt='군민이 행복한 도시형 농촌 보은', max_width=38000),
    'brand-slogan': dict(file='boeun-brand-slogan.jpg', pixels=(2180, 1656),
                         alt='참 좋아 you 보은', max_width=14500),
}
ASSET_FILES = tuple('assets/branding/' + item['file'] for item in ARTWORK.values())


def artwork_path(name):
    return resource_dir() / 'assets' / 'branding' / ARTWORK[name]['file']


def picture_spec(name, cell_width, row_height):
    artwork = ARTWORK[name]
    pixel_width, pixel_height = artwork['pixels']
    scale = min((cell_width - 700) / pixel_width,
                (row_height - 600) / pixel_height,
                artwork['max_width'] / pixel_width)
    return dict(src='assets/branding/' + artwork['file'], alt=artwork['alt'],
                width=round(pixel_width * scale), height=round(pixel_height * scale))
