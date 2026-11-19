# 给安装包加上通知、定时提醒、后台保活等权限
p = 'android/app/src/main/AndroidManifest.xml'
s = open(p, encoding='utf-8').read()
perms = ['android.permission.POST_NOTIFICATIONS', 'android.permission.SCHEDULE_EXACT_ALARM',
         'android.permission.USE_EXACT_ALARM', 'android.permission.RECEIVE_BOOT_COMPLETED',
         'android.permission.WAKE_LOCK', 'android.permission.VIBRATE',
         'android.permission.FOREGROUND_SERVICE', 'android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS',
         'android.permission.FOREGROUND_SERVICE_DATA_SYNC', 'android.permission.FOREGROUND_SERVICE_SPECIAL_USE']
add = ''.join('    <uses-permission android:name="%s" />\n' % x for x in perms if x not in s)
s = s.replace('<application', add + '    <application', 1)
open(p, 'w', encoding='utf-8').write(s)
print('manifest patched')
