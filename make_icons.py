# 生成安装包图标（用你仓库里的 icon.png）和通知小图标
import os
from PIL import Image, ImageDraw
res = 'android/app/src/main/res'
if os.path.exists('icon.png'):
    im = Image.open('icon.png').convert('RGBA')
    s = min(im.size)
    im = im.crop(((im.width - s) // 2, (im.height - s) // 2, (im.width + s) // 2, (im.height + s) // 2))
    for d, px in [('mdpi', 48), ('hdpi', 72), ('xhdpi', 96), ('xxhdpi', 144), ('xxxhdpi', 192)]:
        os.makedirs('%s/mipmap-%s' % (res, d), exist_ok=True)
        a = im.resize((px, px), Image.LANCZOS)
        m = Image.new('L', (px, px), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, px - 1, px - 1), radius=int(px * .22), fill=255)
        sq = Image.new('RGBA', (px, px), (0, 0, 0, 0)); sq.paste(a, (0, 0), m)
        sq.save('%s/mipmap-%s/ic_launcher.png' % (res, d))
        m2 = Image.new('L', (px, px), 0)
        ImageDraw.Draw(m2).ellipse((0, 0, px - 1, px - 1), fill=255)
        rd = Image.new('RGBA', (px, px), (0, 0, 0, 0)); rd.paste(a, (0, 0), m2)
        rd.save('%s/mipmap-%s/ic_launcher_round.png' % (res, d))
    for f in ['ic_launcher.xml', 'ic_launcher_round.xml']:
        p = '%s/mipmap-anydpi-v26/%s' % (res, f)
        if os.path.exists(p):
            os.remove(p)
    print('icon done')
else:
    print('no icon.png, skip')
# 通知栏小图标：白色对话气泡
for d, px in [('mdpi', 24), ('hdpi', 36), ('xhdpi', 48), ('xxhdpi', 72), ('xxxhdpi', 96)]:
    os.makedirs('%s/drawable-%s' % (res, d), exist_ok=True)
    im = Image.new('RGBA', (px, px), (0, 0, 0, 0)); dr = ImageDraw.Draw(im)
    dr.rounded_rectangle((px * .1, px * .14, px * .9, px * .72), radius=px * .22, fill=(255, 255, 255, 255))
    dr.polygon([(px * .28, px * .66), (px * .28, px * .9), (px * .5, px * .7)], fill=(255, 255, 255, 255))
    im.save('%s/drawable-%s/ic_stat_notify.png' % (res, d))
print('notify icon done')
