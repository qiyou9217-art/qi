# 给安装包加上：通知/定时提醒/后台保活权限，以及「真实手机应用上锁」的原生部分（无障碍服务 + 小插件）
import glob, os, re

# ---------- 1. 权限、应用列表可见、上锁服务 ----------
p = 'android/app/src/main/AndroidManifest.xml'
s = open(p, encoding='utf-8').read()
perms = ['android.permission.POST_NOTIFICATIONS', 'android.permission.SCHEDULE_EXACT_ALARM',
         'android.permission.USE_EXACT_ALARM', 'android.permission.RECEIVE_BOOT_COMPLETED',
         'android.permission.WAKE_LOCK', 'android.permission.VIBRATE',
         'android.permission.FOREGROUND_SERVICE', 'android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS',
         'android.permission.FOREGROUND_SERVICE_DATA_SYNC', 'android.permission.FOREGROUND_SERVICE_SPECIAL_USE',
         'android.permission.QUERY_ALL_PACKAGES']
add = ''.join('    <uses-permission android:name="%s" />\n' % x for x in perms if x not in s)
if '<queries>' not in s:
    add += ('    <queries>\n        <intent>\n            <action android:name="android.intent.action.MAIN" />\n'
            '            <category android:name="android.intent.category.LAUNCHER" />\n        </intent>\n    </queries>\n')
s = s.replace('<application', add + '    <application', 1)
if 'LockService' not in s:
    svc = ('        <service android:name=".LockService" android:exported="true" android:label="Celyra 应用上锁"\n'
           '            android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE">\n'
           '            <intent-filter>\n                <action android:name="android.accessibilityservice.AccessibilityService" />\n            </intent-filter>\n'
           '            <meta-data android:name="android.accessibilityservice" android:resource="@xml/celyra_lock_service" />\n'
           '        </service>\n    ')
    s = s.replace('</application>', svc + '</application>', 1)
open(p, 'w', encoding='utf-8').write(s)
print('manifest patched')

# ---------- 2. 资源文件 ----------
res = 'android/app/src/main/res'
os.makedirs(res + '/xml', exist_ok=True)
os.makedirs(res + '/values', exist_ok=True)
open(res + '/xml/celyra_lock_service.xml', 'w', encoding='utf-8').write(
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<accessibility-service xmlns:android="http://schemas.android.com/apk/res/android"\n'
    '    android:accessibilityEventTypes="typeWindowStateChanged"\n'
    '    android:accessibilityFeedbackType="feedbackGeneric"\n'
    '    android:canRetrieveWindowContent="false"\n'
    '    android:notificationTimeout="50"\n'
    '    android:description="@string/celyra_lock_desc" />\n')
open(res + '/values/celyra_lock.xml', 'w', encoding='utf-8').write(
    '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
    '    <string name="celyra_lock_desc">开启后，Celyra 里被好友限制的真实手机应用，一打开就会被送回桌面。只检测当前打开的是哪个应用，不读取任何内容。</string>\n'
    '</resources>\n')

# ---------- 3. Java 代码（放在跟 MainActivity 同一个包里） ----------
main = glob.glob('android/app/src/main/java/**/MainActivity.java', recursive=True)[0]
pkg = re.search(r'package\s+([\w.]+)\s*;', open(main, encoding='utf-8').read()).group(1)
d = os.path.dirname(main)

open(main, 'w', encoding='utf-8').write('''package %(pkg)s;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(CelyraLockPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
''' % {'pkg': pkg})

open(d + '/LockService.java', 'w', encoding='utf-8').write('''package %(pkg)s;

import android.accessibilityservice.AccessibilityService;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;
import android.view.accessibility.AccessibilityEvent;
import android.widget.Toast;
import java.util.Set;

/** 检测当前打开的应用；如果它在「被限制」名单里，就送回桌面并提示 */
public class LockService extends AccessibilityService {
    private long lastKick = 0;

    @Override
    public void onAccessibilityEvent(AccessibilityEvent e) {
        try {
            if (e == null || e.getEventType() != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) return;
            CharSequence p = e.getPackageName();
            if (p == null) return;
            String pkg = p.toString();
            if (pkg.equals(getPackageName())) return;
            SharedPreferences sp = getSharedPreferences("celyra_lock", MODE_PRIVATE);
            if (!sp.getBoolean("on", false)) return;
            Set<String> set = sp.getStringSet("pkgs", null);
            if (set == null || !set.contains(pkg)) return;
            long now = System.currentTimeMillis();
            if (now - lastKick < 500) return;
            lastKick = now;
            performGlobalAction(GLOBAL_ACTION_HOME);
            final String msg = "此应用已被 " + sp.getString("by", "TA") + " 限制";
            new Handler(Looper.getMainLooper()).post(new Runnable() {
                @Override
                public void run() {
                    Toast.makeText(getApplicationContext(), msg, Toast.LENGTH_SHORT).show();
                }
            });
        } catch (Throwable t) {
            // 出任何问题都不影响手机正常使用
        }
    }

    @Override
    public void onInterrupt() {
    }
}
''' % {'pkg': pkg})

open(d + '/CelyraLockPlugin.java', 'w', encoding='utf-8').write('''package %(pkg)s;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.drawable.Drawable;
import android.net.Uri;
import android.provider.Settings;
import android.util.Base64;
import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.ByteArrayOutputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

@CapacitorPlugin(name = "CelyraLock")
public class CelyraLockPlugin extends Plugin {

    /** 无障碍服务有没有被用户打开 */
    static boolean serviceEnabled(Context ctx) {
        try {
            String s = Settings.Secure.getString(ctx.getContentResolver(), Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
            if (s == null) return false;
            String low = s.toLowerCase();
            String full = (ctx.getPackageName() + "/" + LockService.class.getName()).toLowerCase();
            String shortName = (ctx.getPackageName() + "/." + LockService.class.getSimpleName()).toLowerCase();
            return low.contains(full) || low.contains(shortName);
        } catch (Throwable t) {
            return false;
        }
    }

    private void start(Intent i, PluginCall call) {
        try {
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            getContext().startActivity(i);
            call.resolve();
        } catch (Throwable t) {
            call.reject("打不开系统设置页");
        }
    }

    @PluginMethod
    public void status(PluginCall call) {
        JSObject o = new JSObject();
        o.put("enabled", serviceEnabled(getContext()));
        call.resolve(o);
    }

    @PluginMethod
    public void openSettings(PluginCall call) {
        start(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS), call);
    }

    @PluginMethod
    public void openAppInfo(PluginCall call) {
        start(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + getContext().getPackageName())), call);
    }

    /** 手机里能在桌面打开的应用（名字 + 包名 + 小图标） */
    @PluginMethod
    public void getApps(PluginCall call) {
        try {
            Context ctx = getContext();
            PackageManager pm = ctx.getPackageManager();
            Intent q = new Intent(Intent.ACTION_MAIN);
            q.addCategory(Intent.CATEGORY_LAUNCHER);
            List<ResolveInfo> list = pm.queryIntentActivities(q, 0);

            String home = "";
            try {
                Intent h = new Intent(Intent.ACTION_MAIN);
                h.addCategory(Intent.CATEGORY_HOME);
                ResolveInfo hr = pm.resolveActivity(h, PackageManager.MATCH_DEFAULT_ONLY);
                if (hr != null && hr.activityInfo != null) home = hr.activityInfo.packageName;
            } catch (Throwable ignore) {
            }

            final List<JSObject> out = new ArrayList<JSObject>();
            Set<String> seen = new HashSet<String>();
            for (ResolveInfo ri : list) {
                String pkg = ri.activityInfo.packageName;
                String low = pkg.toLowerCase();
                // 不让锁：自己、桌面、系统设置、系统界面、电话
                if (pkg.equals(ctx.getPackageName()) || pkg.equals(home)) continue;
                if (low.contains(".settings") || low.contains("systemui") || low.contains("dialer") || low.contains("incallui")) continue;
                if (!seen.add(pkg)) continue;
                JSObject o = new JSObject();
                o.put("pkg", pkg);
                o.put("label", String.valueOf(ri.loadLabel(pm)));
                try {
                    Drawable dr = ri.loadIcon(pm);
                    Bitmap bmp = Bitmap.createBitmap(64, 64, Bitmap.Config.ARGB_8888);
                    Canvas cv = new Canvas(bmp);
                    dr.setBounds(0, 0, 64, 64);
                    dr.draw(cv);
                    ByteArrayOutputStream bo = new ByteArrayOutputStream();
                    bmp.compress(Bitmap.CompressFormat.PNG, 100, bo);
                    o.put("icon", "data:image/png;base64," + Base64.encodeToString(bo.toByteArray(), Base64.NO_WRAP));
                } catch (Throwable ignore) {
                }
                out.add(o);
            }
            Collections.sort(out, new Comparator<JSObject>() {
                @Override
                public int compare(JSObject a, JSObject b) {
                    return a.getString("label", "").compareToIgnoreCase(b.getString("label", ""));
                }
            });
            JSArray arr = new JSArray();
            for (JSObject o : out) arr.put(o);
            JSObject res = new JSObject();
            res.put("apps", arr);
            call.resolve(res);
        } catch (Throwable t) {
            call.reject("读取应用列表失败");
        }
    }

    /** 同步「现在要锁哪些应用」给无障碍服务 */
    @PluginMethod
    public void setLocked(PluginCall call) {
        try {
            Set<String> set = new HashSet<String>();
            JSArray arr = call.getArray("pkgs");
            if (arr != null) {
                for (int i = 0; i < arr.length(); i++) set.add(arr.getString(i));
            }
            boolean on = call.getBoolean("on", false);
            String by = call.getString("by", "TA");
            SharedPreferences sp = getContext().getSharedPreferences("celyra_lock", Context.MODE_PRIVATE);
            sp.edit().putBoolean("on", on).putStringSet("pkgs", set).putString("by", by).apply();
            call.resolve();
        } catch (Throwable t) {
            call.reject("同步失败");
        }
    }
}
''' % {'pkg': pkg})
print('lock plugin written in', d)
