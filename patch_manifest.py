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
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.ColorMatrix;
import android.graphics.ColorMatrixColorFilter;
import android.graphics.PixelFormat;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityEvent;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.util.Set;

/** 检测当前打开的应用；如果它在「被限制」名单里，就盖上一层黑灰色的「此应用已被 TA 限制」界面 */
public class LockService extends AccessibilityService {
    private WindowManager wm;
    private View overlay;
    private String shownPkg = "";

    @Override
    public void onAccessibilityEvent(AccessibilityEvent e) {
        try {
            if (e == null || e.getEventType() != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) return;
            CharSequence p = e.getPackageName();
            if (p == null) return;
            String pkg = p.toString();
            if (pkg.equals(getPackageName())) return;
            String low = pkg.toLowerCase();
            // 下拉通知栏、输入法弹出时，不改变当前状态
            if (low.contains("systemui") || low.contains("inputmethod")) return;
            SharedPreferences sp = getSharedPreferences("celyra_lock", MODE_PRIVATE);
            Set<String> set = sp.getStringSet("pkgs", null);
            if (sp.getBoolean("on", false) && set != null && set.contains(pkg)) {
                showOverlay(pkg, sp.getString("by", "TA"));
            } else {
                hideOverlay();
            }
        } catch (Throwable t) {
            // 出任何问题都不影响手机正常使用
        }
    }

    private TextView pill(String text, int bg, int fg, float d) {
        TextView b = new TextView(this);
        b.setText(text);
        b.setTextColor(fg);
        b.setTextSize(16f);
        b.setTypeface(Typeface.DEFAULT_BOLD);
        b.setGravity(Gravity.CENTER);
        GradientDrawable g = new GradientDrawable();
        g.setColor(bg);
        g.setCornerRadius(25 * d);
        b.setBackground(g);
        return b;
    }

    private void showOverlay(String pkg, String by) {
        if (overlay != null && pkg.equals(shownPkg)) return;
        hideOverlay();
        final float d = getResources().getDisplayMetrics().density;
        String label = pkg;
        Drawable icon = null;
        try {
            PackageManager pm = getPackageManager();
            label = String.valueOf(pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)));
            icon = pm.getApplicationIcon(pkg);
        } catch (Throwable ignore) {
        }

        FrameLayout root = new FrameLayout(this);
        GradientDrawable bg = new GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
                new int[]{0xFF3A3A3C, 0xFF1C1C1E, 0xFF000000});
        root.setBackground(bg);
        root.setClickable(true);

        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setGravity(Gravity.CENTER_HORIZONTAL);
        int pad = (int) (28 * d);
        col.setPadding(pad, 0, pad, 0);

        FrameLayout box = new FrameLayout(this);
        ImageView iv = new ImageView(this);
        if (icon != null) {
            iv.setImageDrawable(icon);
            ColorMatrix cm = new ColorMatrix();
            cm.setSaturation(0f);
            ColorMatrix dim = new ColorMatrix();
            dim.setScale(0.55f, 0.55f, 0.55f, 1f);
            cm.postConcat(dim);
            iv.setColorFilter(new ColorMatrixColorFilter(cm));
        }
        box.addView(iv, new FrameLayout.LayoutParams((int) (88 * d), (int) (88 * d), Gravity.CENTER));
        TextView badge = new TextView(this);
        badge.setText("\\uD83D\\uDD12");
        badge.setTextSize(15f);
        badge.setGravity(Gravity.CENTER);
        GradientDrawable bgd = new GradientDrawable();
        bgd.setColor(0xFFFFFFFF);
        bgd.setCornerRadius(18 * d);
        badge.setBackground(bgd);
        box.addView(badge, new FrameLayout.LayoutParams((int) (36 * d), (int) (36 * d), Gravity.BOTTOM | Gravity.END));
        col.addView(box, new LinearLayout.LayoutParams((int) (104 * d), (int) (104 * d)));

        TextView t1 = new TextView(this);
        t1.setText("此应用已被 " + by + " 限制");
        t1.setTextColor(0xFFFFFFFF);
        t1.setTextSize(21f);
        t1.setTypeface(Typeface.DEFAULT_BOLD);
        t1.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams l1 = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        l1.topMargin = (int) (20 * d);
        col.addView(t1, l1);

        TextView t2 = new TextView(this);
        t2.setText("「" + label + "」暂时无法打开\\n可以去聊天里请 TA 解锁");
        t2.setTextColor(0xFFA1A1A6);
        t2.setTextSize(14f);
        t2.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams l2 = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        l2.topMargin = (int) (10 * d);
        col.addView(t2, l2);

        root.addView(col, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.CENTER));

        LinearLayout bottom = new LinearLayout(this);
        bottom.setOrientation(LinearLayout.VERTICAL);
        bottom.setGravity(Gravity.CENTER_HORIZONTAL);
        TextView go = pill("去聊天请求解锁", 0xFFFFFFFF, 0xFF000000, d);
        TextView back = pill("返回", 0x1FFFFFFF, 0xFFFFFFFF, d);
        LinearLayout.LayoutParams lb = new LinearLayout.LayoutParams((int) (300 * d), (int) (50 * d));
        LinearLayout.LayoutParams lb2 = new LinearLayout.LayoutParams((int) (300 * d), (int) (50 * d));
        lb2.topMargin = (int) (12 * d);
        bottom.addView(go, lb);
        bottom.addView(back, lb2);
        FrameLayout.LayoutParams lp0 = new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL);
        lp0.bottomMargin = (int) (56 * d);
        root.addView(bottom, lp0);

        go.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                openChat();
            }
        });
        back.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                performGlobalAction(GLOBAL_ACTION_HOME);
                hideOverlay();
            }
        });

        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT);
        wm = (WindowManager) getSystemService(Context.WINDOW_SERVICE);
        wm.addView(root, lp);
        overlay = root;
        shownPkg = pkg;
    }

    private void hideOverlay() {
        if (overlay != null) {
            try {
                wm.removeView(overlay);
            } catch (Throwable ignore) {
            }
            overlay = null;
            shownPkg = "";
        }
    }

    /** 回到 Celyra，并让页面自动跳到智能遥控的聊天 */
    private void openChat() {
        try {
            getSharedPreferences("celyra_lock", MODE_PRIVATE).edit().putBoolean("goChat", true).apply();
            hideOverlay();
            Intent i = new Intent(this, MainActivity.class);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
            startActivity(i);
        } catch (Throwable t) {
            performGlobalAction(GLOBAL_ACTION_HOME);
        }
    }

    @Override
    public void onInterrupt() {
        hideOverlay();
    }

    @Override
    public void onDestroy() {
        hideOverlay();
        super.onDestroy();
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

    /** 点了「去聊天请求解锁」之后，页面来问一下要不要自动跳到聊天 */
    @PluginMethod
    public void popGoChat(PluginCall call) {
        boolean g = false;
        try {
            SharedPreferences sp = getContext().getSharedPreferences("celyra_lock", Context.MODE_PRIVATE);
            g = sp.getBoolean("goChat", false);
            if (g) sp.edit().putBoolean("goChat", false).apply();
        } catch (Throwable ignore) {
        }
        JSObject o = new JSObject();
        o.put("go", g);
        call.resolve(o);
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
