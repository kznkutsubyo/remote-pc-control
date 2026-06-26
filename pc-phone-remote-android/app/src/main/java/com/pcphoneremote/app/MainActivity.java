package com.pcphoneremote.app;

import android.animation.AnimatorSet;
import android.animation.ObjectAnimator;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.animation.DecelerateInterpolator;
import android.view.inputmethod.InputMethodManager;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.GridLayout;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class MainActivity extends Activity {
    private static final String PREFS = "pc_remote_settings";
    private static final String PREF_PROFILES = "device_profiles";
    private static final String PREF_SELECTED_PROFILE = "selected_profile";
    private static final String PREF_TAB = "selected_tab";
    private static final String PREF_LIGHT_THEME = "light_theme";
    private static final String DEFAULT_HOST = "192.168.1.25";
    private static final String DEFAULT_PORT = "8765";
    private static final String DEFAULT_PIN = "";

    private int BG = Color.rgb(7, 7, 14);
    private int PANEL = Color.rgb(18, 18, 30);
    private int PANEL_2 = Color.rgb(27, 24, 43);
    private int TEXT = Color.rgb(248, 247, 255);
    private int MUTED = Color.rgb(153, 148, 171);
    private int LINE = Color.rgb(55, 49, 79);
    private int ACCENT = Color.rgb(161, 105, 255);
    private int ACCENT_DARK = Color.rgb(96, 61, 180);
    private int WARN = Color.rgb(235, 174, 86);
    private int DANGER = Color.rgb(239, 92, 121);
    private int SUCCESS = Color.rgb(75, 224, 163);
    private boolean lightTheme;

    private static final String[] LANG_CODES = {"en", "ru", "uk", "sk", "cs", "ja", "de", "es", "fr", "pl"};
    private static final String[] LANG_NAMES = {
            "English",
            "\u0420\u0443\u0441\u0441\u043a\u0438\u0439",
            "\u0423\u043a\u0440\u0430\u0457\u043d\u0441\u044c\u043a\u0430",
            "Sloven\u010dina",
            "\u010ce\u0161tina",
            "\u65e5\u672c\u8a9e",
            "Deutsch",
            "Espa\u00f1ol",
            "Fran\u00e7ais",
            "Polski"
    };

    private EditText profileNameInput;
    private EditText hostInput;
    private EditText portInput;
    private EditText pinInput;
    private Spinner profileSpinner;
    private TextView statusView;
    private TextView statusDot;
    private SharedPreferences prefs;
    private String sessionCookie;
    private boolean languageReady;
    private boolean profileReady;
    private List<DeviceProfile> profiles = new ArrayList<>();
    private int selectedProfileIndex;
    private int currentTab;
    private final Handler ui = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        rebuildContent(true);
    }

    private void rebuildContent(boolean animate) {
        View content = buildContent();
        setContentView(content);
        if (animate) {
            animateScreen(content);
        }
    }

    private View buildContent() {
        applyTheme();
        languageReady = false;
        profileReady = false;
        profiles = loadProfiles();
        selectedProfileIndex = prefs.getInt(PREF_SELECTED_PROFILE, 0);
        if (selectedProfileIndex < 0 || selectedProfileIndex >= profiles.size()) {
            selectedProfileIndex = 0;
        }
        currentTab = prefs.getInt(PREF_TAB, 0);
        if (currentTab < 0 || currentTab > 2) {
            currentTab = 0;
        }

        LinearLayout screen = vertical();
        screen.setBackgroundColor(BG);

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(BG);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(18), dp(30), dp(18), dp(18));
        scroll.addView(root, new ScrollView.LayoutParams(
                ScrollView.LayoutParams.MATCH_PARENT,
                ScrollView.LayoutParams.WRAP_CONTENT
        ));
        screen.addView(scroll, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                0,
                1f
        ));

        LinearLayout hero = vertical();
        hero.setPadding(dp(2), 0, dp(2), dp(18));
        root.addView(hero);

        TextView eyebrow = text(tr("eyebrow"), 12, ACCENT, Typeface.BOLD);
        eyebrow.setLetterSpacing(0.08f);
        hero.addView(eyebrow);

        TextView title = text("PC Remote", 32, TEXT, Typeface.BOLD);
        title.setPadding(0, dp(4), 0, dp(4));
        hero.addView(title);

        TextView subtitle = text(tr("subtitle"), 15, MUTED, Typeface.NORMAL);
        subtitle.setLineSpacing(dp(2), 1.0f);
        hero.addView(subtitle);

        LinearLayout statusPanel = horizontal();
        statusPanel.setGravity(Gravity.CENTER_VERTICAL);
        statusPanel.setPadding(dp(14), dp(12), dp(14), dp(12));
        statusPanel.setBackground(panelBg(PANEL_2, subtleStroke(), 8));
        LinearLayout.LayoutParams statusParams = matchWrap();
        statusParams.setMargins(0, 0, 0, dp(14));
        root.addView(statusPanel, statusParams);

        statusDot = new TextView(this);
        statusDot.setText("");
        statusDot.setBackground(ovalBg(ACCENT));
        LinearLayout.LayoutParams dotParams = new LinearLayout.LayoutParams(dp(10), dp(10));
        dotParams.setMargins(0, 0, dp(10), 0);
        statusPanel.addView(statusDot, dotParams);

        statusView = text(tr("ready"), 14, MUTED, Typeface.NORMAL);
        statusPanel.addView(statusView, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

        if (currentTab == 0) {
            buildRemoteTab(root);
        } else if (currentTab == 1) {
            buildDevicesTab(root);
        } else {
            buildSettingsTab(root);
        }

        addBottomTabs(screen);
        return screen;
    }

    private void buildSettingsTab(LinearLayout root) {
        LinearLayout themeCard = card(root, tr("themeTitle"), tr("themeSubtitle"));
        themeCard.addView(themeToggle(), matchWrap());

        LinearLayout languageCard = card(root, tr("languageTitle"), tr("languageSubtitle"));
        TextView languageLabel = text(tr("languageLabel"), 13, labelColor(), Typeface.BOLD);
        languageLabel.setPadding(dp(2), 0, dp(2), dp(6));
        languageCard.addView(languageLabel);
        Spinner languageSpinner = new Spinner(this);
        ArrayAdapter<String> adapter = languageAdapter();
        languageSpinner.setAdapter(adapter);
        languageSpinner.setSelection(languageIndex(lang()), false);
        languageSpinner.setBackground(panelBg(fieldBg(), subtleStroke(), 8));
        languageSpinner.setPadding(dp(10), 0, dp(10), 0);
        languageCard.addView(languageSpinner, inputParams());
        languageSpinner.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                if (!languageReady) {
                    languageReady = true;
                    return;
                }
                saveSettings();
                prefs.edit().putString("lang", LANG_CODES[position]).apply();
                rebuildContent(false);
                setStatus(tr("languageSaved"), ACCENT);
            }

            @Override
            public void onNothingSelected(AdapterView<?> parent) {
            }
        });
    }

    private View themeToggle() {
        FrameLayout frame = new FrameLayout(this);
        frame.setBackground(panelBg(lightTheme ? Color.rgb(231, 235, 245) : Color.rgb(12, 12, 22), lightTheme ? Color.rgb(208, 215, 230) : Color.rgb(38, 34, 57), 18));
        frame.setPadding(dp(6), dp(6), dp(6), dp(6));

        TextView thumb = new TextView(this);
        thumb.setBackground(gradientBg(lightTheme ? Color.rgb(119, 93, 255) : Color.rgb(122, 78, 220), lightTheme ? Color.rgb(92, 142, 255) : Color.rgb(74, 45, 145), ACCENT, 14));
        frame.addView(thumb, new FrameLayout.LayoutParams(1, dp(48), Gravity.LEFT | Gravity.CENTER_VERTICAL));
        frame.post(() -> {
            int availableWidth = frame.getWidth() - dp(12);
            int thumbWidth = availableWidth / 2;
            ViewGroup.LayoutParams params = thumb.getLayoutParams();
            params.width = thumbWidth;
            thumb.setLayoutParams(params);
            thumb.setTranslationX(lightTheme ? thumbWidth : 0);
        });

        LinearLayout shell = horizontal();
        shell.setGravity(Gravity.CENTER);
        frame.addView(shell, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
        ));

        TextView dark = themeOption(tr("themeDark"), !lightTheme);
        TextView light = themeOption(tr("themeLight"), lightTheme);

        dark.setOnClickListener(v -> setThemeMode(false, thumb, frame));
        light.setOnClickListener(v -> setThemeMode(true, thumb, frame));

        shell.addView(dark);
        shell.addView(light);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(60)
        );
        params.setMargins(0, 0, 0, dp(12));
        frame.setLayoutParams(params);
        return frame;
    }

    private TextView themeOption(String label, boolean active) {
        TextView option = new TextView(this);
        option.setText(label);
        option.setGravity(Gravity.CENTER);
        option.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        option.setTextSize(14);
        option.setTextColor(active ? TEXT : MUTED);
        option.setBackgroundColor(Color.TRANSPARENT);
        option.setClickable(true);
        option.setFocusable(true);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, dp(48), 1f);
        option.setLayoutParams(params);
        return option;
    }

    private void setThemeMode(boolean useLightTheme, View thumb, View frame) {
        if (lightTheme == useLightTheme) {
            animateTap(frame);
            return;
        }
        int availableWidth = frame.getWidth() - dp(12);
        int thumbWidth = availableWidth / 2;
        thumb.animate()
                .translationX(useLightTheme ? thumbWidth : 0)
                .setDuration(260)
                .setInterpolator(new DecelerateInterpolator())
                .start();
        prefs.edit().putBoolean(PREF_LIGHT_THEME, useLightTheme).apply();
        ui.postDelayed(() -> rebuildContent(false), 280);
    }

    private void buildDevicesTab(LinearLayout root) {
        DeviceProfile selectedProfile = profiles.get(selectedProfileIndex);
        LinearLayout settingsCard = card(root, tr("profilesTitle"), tr("profilesSubtitle"));
        TextView profileLabel = text(tr("profileSelectLabel"), 13, labelColor(), Typeface.BOLD);
        profileLabel.setPadding(dp(2), 0, dp(2), dp(6));
        settingsCard.addView(profileLabel);

        profileSpinner = new Spinner(this);
        profileSpinner.setAdapter(profileAdapter());
        profileSpinner.setSelection(selectedProfileIndex, false);
        profileSpinner.setBackground(panelBg(fieldBg(), subtleStroke(), 8));
        profileSpinner.setPadding(dp(10), 0, dp(10), 0);
        settingsCard.addView(profileSpinner, inputParams());

        profileNameInput = labeledInput(settingsCard, tr("profileNameLabel"), tr("profileNameHint"), selectedProfile.name);
        hostInput = labeledInput(settingsCard, tr("hostLabel"), tr("hostHint"), selectedProfile.host);
        portInput = labeledInput(settingsCard, tr("portLabel"), tr("portHint"), selectedProfile.port);
        pinInput = labeledInput(settingsCard, "PIN", tr("pinHint"), selectedProfile.pin);
        portInput.setInputType(InputType.TYPE_CLASS_NUMBER);
        pinInput.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_VARIATION_PASSWORD);

        profileSpinner.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                if (!profileReady) {
                    profileReady = true;
                    return;
                }
                selectedProfileIndex = position;
                prefs.edit().putInt(PREF_SELECTED_PROFILE, selectedProfileIndex).apply();
                fillProfile(profiles.get(position));
                saveSettings();
                setStatus(tr("profileSelected"), ACCENT);
            }

            @Override
            public void onNothingSelected(AdapterView<?> parent) {
            }
        });

        TextView save = actionButton(tr("saveProfileTitle"), tr("saveProfileSub"), ACCENT, Color.rgb(7, 24, 17));
        save.setOnClickListener(v -> {
            animateTap(v);
            saveCurrentProfile();
            hideKeyboard();
            setStatus(tr("profileSaved"), ACCENT);
        });
        settingsCard.addView(save);

        LinearLayout profileButtons = horizontal();
        settingsCard.addView(profileButtons, matchWrap());

        TextView addProfile = actionButton(tr("addProfileTitle"), tr("addProfileSub"), PANEL_2, TEXT);
        LinearLayout.LayoutParams addParams = new LinearLayout.LayoutParams(0, dp(58), 1f);
        addParams.setMargins(0, dp(8), dp(4), 0);
        addProfile.setLayoutParams(addParams);
        addProfile.setOnClickListener(v -> {
            animateTap(v);
            createProfile();
            hideKeyboard();
        });
        profileButtons.addView(addProfile);

        TextView deleteProfile = actionButton(tr("deleteProfileTitle"), tr("deleteProfileSub"), Color.rgb(92, 42, 42), TEXT);
        LinearLayout.LayoutParams deleteParams = new LinearLayout.LayoutParams(0, dp(58), 1f);
        deleteParams.setMargins(dp(4), dp(8), 0, 0);
        deleteProfile.setLayoutParams(deleteParams);
        deleteProfile.setOnClickListener(v -> {
            animateTap(v);
            deleteCurrentProfile();
            hideKeyboard();
        });
        profileButtons.addView(deleteProfile);

        TextView test = actionButton(tr("testTitle"), tr("testSub"), Color.rgb(34, 30, 54), TEXT);
        test.setOnClickListener(v -> {
            animateTap(v);
            saveSettings();
            hideKeyboard();
            runRequest("health", null);
        });
        settingsCard.addView(test);
    }

    private void buildRemoteTab(LinearLayout root) {
        DeviceProfile profile = profiles.get(selectedProfileIndex);
        LinearLayout selectedCard = vertical();
        selectedCard.setPadding(dp(18), dp(18), dp(18), dp(18));
        selectedCard.setBackground(lightTheme
                ? gradientBg(Color.rgb(255, 255, 255), Color.rgb(232, 239, 255), Color.rgb(197, 211, 245), 8)
                : gradientBg(Color.rgb(32, 24, 59), Color.rgb(18, 18, 30), Color.rgb(102, 67, 181), 8));
        LinearLayout.LayoutParams selectedParams = matchWrap();
        selectedParams.setMargins(0, 0, 0, dp(14));
        root.addView(selectedCard, selectedParams);

        TextView selectedTitle = text(tr("selectedDeviceTitle"), 13, lightTheme ? ACCENT_DARK : Color.rgb(200, 178, 255), Typeface.BOLD);
        selectedTitle.setLetterSpacing(0.05f);
        selectedCard.addView(selectedTitle);

        TextView name = text(profile.name, 22, TEXT, Typeface.BOLD);
        name.setPadding(0, dp(8), 0, 0);
        selectedCard.addView(name);

        TextView endpoint = text(endpointFor(profile), 14, MUTED, Typeface.NORMAL);
        endpoint.setPadding(0, dp(6), 0, dp(8));
        selectedCard.addView(endpoint);

        TextView switchDevice = actionButton(tr("switchDeviceTitle"), tr("switchDeviceSub"), ACCENT_DARK, TEXT);
        switchDevice.setOnClickListener(v -> {
            animateTap(v);
            prefs.edit().putInt(PREF_TAB, 1).apply();
            rebuildContent(false);
        });
        selectedCard.addView(switchDevice);

        LinearLayout controlsCard = card(root, tr("controlsTitle"), tr("controlsSubtitle"));
        GridLayout grid = new GridLayout(this);
        grid.setColumnCount(2);
        grid.setPadding(0, dp(2), 0, 0);
        controlsCard.addView(grid, matchWrap());

        addCommandButton(grid, tr("muteTitle"), "mute", false, ACCENT_DARK, 2, R.drawable.ic_action_mute);
        addCommandButton(grid, tr("lockTitle"), "lock", false, Color.rgb(34, 30, 54), 1, R.drawable.ic_action_lock);
        addCommandButton(grid, tr("sleepTitle"), "sleep", true, Color.rgb(70, 54, 91), 1, R.drawable.ic_action_sleep);
        addCommandButton(grid, tr("restartTitle"), "restart", true, Color.rgb(74, 58, 98), 1, R.drawable.ic_action_restart);
        addCommandButton(grid, tr("shutdownTitle"), "shutdown", true, Color.rgb(87, 41, 61), 1, R.drawable.ic_action_power);

        TextView note = text(tr("note"), 13, MUTED, Typeface.NORMAL);
        note.setPadding(dp(2), dp(12), dp(2), 0);
        note.setLineSpacing(dp(2), 1.0f);
        controlsCard.addView(note);
    }

    private void addBottomTabs(LinearLayout root) {
        LinearLayout tabs = horizontal();
        tabs.setGravity(Gravity.CENTER);
        tabs.setPadding(dp(24), dp(10), dp(24), dp(14));
        tabs.setBackgroundColor(bottomBarBg());
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(84)
        );
        root.addView(tabs, params);

        tabs.addView(tabButton(0, R.drawable.ic_remote_tab, tr("tabRemote")));
        tabs.addView(tabButton(1, R.drawable.ic_devices_tab, tr("tabDevices")));
        tabs.addView(tabButton(2, R.drawable.ic_settings_tab, tr("tabSettings")));
    }

    private ImageButton tabButton(int tab, int iconRes, String label) {
        boolean active = currentTab == tab;
        ImageButton button = new ImageButton(this);
        button.setImageResource(iconRes);
        button.setColorFilter(active ? ACCENT : (lightTheme ? Color.rgb(129, 139, 157) : Color.rgb(225, 226, 235)));
        button.setBackgroundColor(Color.TRANSPARENT);
        button.setPadding(dp(18), dp(14), dp(18), dp(14));
        button.setContentDescription(label);
        button.setScaleType(android.widget.ImageView.ScaleType.CENTER);
        button.setClickable(true);
        button.setFocusable(true);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, dp(60), 1f);
        params.setMargins(dp(10), 0, dp(10), 0);
        button.setLayoutParams(params);
        button.setOnClickListener(v -> {
            animateTap(v);
            prefs.edit().putInt(PREF_TAB, tab).apply();
            rebuildContent(false);
        });
        return button;
    }

    private DeviceProfile activeProfile() {
        if (profiles == null || profiles.isEmpty()) {
            profiles = loadProfiles();
        }
        if (selectedProfileIndex < 0 || selectedProfileIndex >= profiles.size()) {
            selectedProfileIndex = 0;
        }
        return profiles.get(selectedProfileIndex);
    }

    private String endpointFor(DeviceProfile profile) {
        if (profile.host.startsWith("http://") || profile.host.startsWith("https://")) {
            return profile.host;
        }
        return profile.host + ":" + profile.port;
    }

    private LinearLayout card(LinearLayout root, String title, String subtitle) {
        LinearLayout card = vertical();
        card.setPadding(dp(16), dp(16), dp(16), dp(16));
        card.setBackground(panelBg(PANEL, subtleStroke(), 8));
        LinearLayout.LayoutParams params = matchWrap();
        params.setMargins(0, 0, 0, dp(14));
        root.addView(card, params);

        TextView titleView = text(title, 18, TEXT, Typeface.BOLD);
        card.addView(titleView);

        TextView subtitleView = text(subtitle, 13, MUTED, Typeface.NORMAL);
        subtitleView.setPadding(0, dp(4), 0, dp(12));
        subtitleView.setLineSpacing(dp(2), 1.0f);
        card.addView(subtitleView);

        return card;
    }

    private void applyTheme() {
        lightTheme = prefs.getBoolean(PREF_LIGHT_THEME, false);
        if (lightTheme) {
            BG = Color.rgb(247, 249, 253);
            PANEL = Color.rgb(255, 255, 255);
            PANEL_2 = Color.rgb(239, 243, 250);
            TEXT = Color.rgb(18, 22, 32);
            MUTED = Color.rgb(102, 112, 132);
            LINE = Color.rgb(218, 224, 235);
            ACCENT = Color.rgb(67, 127, 255);
            ACCENT_DARK = Color.rgb(42, 104, 224);
            WARN = Color.rgb(225, 146, 46);
            DANGER = Color.rgb(224, 78, 100);
            SUCCESS = Color.rgb(34, 181, 130);
        } else {
            BG = Color.rgb(7, 7, 14);
            PANEL = Color.rgb(18, 18, 30);
            PANEL_2 = Color.rgb(27, 24, 43);
            TEXT = Color.rgb(248, 247, 255);
            MUTED = Color.rgb(153, 148, 171);
            LINE = Color.rgb(55, 49, 79);
            ACCENT = Color.rgb(161, 105, 255);
            ACCENT_DARK = Color.rgb(96, 61, 180);
            WARN = Color.rgb(235, 174, 86);
            DANGER = Color.rgb(239, 92, 121);
            SUCCESS = Color.rgb(75, 224, 163);
        }
    }

    private int fieldBg() {
        return lightTheme ? Color.rgb(247, 249, 253) : Color.rgb(12, 12, 22);
    }

    private int subtleStroke() {
        return lightTheme ? Color.rgb(215, 222, 235) : Color.rgb(38, 34, 57);
    }

    private int bottomBarBg() {
        return lightTheme ? Color.rgb(255, 255, 255) : Color.rgb(8, 10, 16);
    }

    private int labelColor() {
        return lightTheme ? Color.rgb(45, 52, 68) : Color.rgb(204, 211, 217);
    }

    private ArrayAdapter<String> languageAdapter() {
        return new ArrayAdapter<String>(this, android.R.layout.simple_spinner_item, LANG_NAMES) {
            @Override
            public View getView(int position, View convertView, ViewGroup parent) {
                TextView view = (TextView) super.getView(position, convertView, parent);
                view.setTextColor(TEXT);
                view.setTextSize(16);
                view.setPadding(dp(8), 0, dp(8), 0);
                view.setBackgroundColor(fieldBg());
                return view;
            }

            @Override
            public View getDropDownView(int position, View convertView, ViewGroup parent) {
                TextView view = (TextView) super.getDropDownView(position, convertView, parent);
                view.setTextColor(TEXT);
                view.setTextSize(16);
                view.setPadding(dp(16), dp(14), dp(16), dp(14));
                view.setBackgroundColor(PANEL_2);
                return view;
            }
        };
    }

    private ArrayAdapter<String> profileAdapter() {
        List<String> names = new ArrayList<>();
        for (DeviceProfile profile : profiles) {
            names.add(profile.name);
        }
        return new ArrayAdapter<String>(this, android.R.layout.simple_spinner_item, names) {
            @Override
            public View getView(int position, View convertView, ViewGroup parent) {
                TextView view = (TextView) super.getView(position, convertView, parent);
                view.setTextColor(TEXT);
                view.setTextSize(16);
                view.setPadding(dp(8), 0, dp(8), 0);
                view.setBackgroundColor(fieldBg());
                return view;
            }

            @Override
            public View getDropDownView(int position, View convertView, ViewGroup parent) {
                TextView view = (TextView) super.getDropDownView(position, convertView, parent);
                view.setTextColor(TEXT);
                view.setTextSize(16);
                view.setPadding(dp(16), dp(14), dp(16), dp(14));
                view.setBackgroundColor(PANEL_2);
                return view;
            }
        };
    }

    private List<DeviceProfile> loadProfiles() {
        List<DeviceProfile> loaded = new ArrayList<>();
        String raw = prefs.getString(PREF_PROFILES, "");
        if (raw != null && !raw.isEmpty()) {
            try {
                JSONArray array = new JSONArray(raw);
                for (int i = 0; i < array.length(); i++) {
                    JSONObject item = array.getJSONObject(i);
                    loaded.add(new DeviceProfile(
                            item.optString("name", tr("defaultProfileName")),
                            item.optString("host", DEFAULT_HOST),
                            item.optString("port", DEFAULT_PORT),
                            item.optString("pin", DEFAULT_PIN)
                    ));
                }
            } catch (JSONException ignored) {
                loaded.clear();
            }
        }

        if (loaded.isEmpty()) {
            loaded.add(new DeviceProfile(
                    tr("defaultProfileName"),
                    prefs.getString("host", DEFAULT_HOST),
                    prefs.getString("port", DEFAULT_PORT),
                    prefs.getString("pin", DEFAULT_PIN)
            ));
        }
        return loaded;
    }

    private void persistProfiles() {
        JSONArray array = new JSONArray();
        try {
            for (DeviceProfile profile : profiles) {
                JSONObject item = new JSONObject();
                item.put("name", profile.name);
                item.put("host", profile.host);
                item.put("port", profile.port);
                item.put("pin", profile.pin);
                array.put(item);
            }
        } catch (JSONException ignored) {
            return;
        }

        prefs.edit()
                .putString(PREF_PROFILES, array.toString())
                .putInt(PREF_SELECTED_PROFILE, selectedProfileIndex)
                .apply();
    }

    private void fillProfile(DeviceProfile profile) {
        profileNameInput.setText(profile.name);
        hostInput.setText(profile.host);
        portInput.setText(profile.port);
        pinInput.setText(profile.pin);
    }

    private DeviceProfile currentInputProfile() {
        String name = profileNameInput.getText().toString().trim();
        if (name.isEmpty()) {
            name = tr("defaultProfileName");
        }
        return new DeviceProfile(
                name,
                hostInput.getText().toString().trim(),
                portInput.getText().toString().trim(),
                pinInput.getText().toString().trim()
        );
    }

    private void saveCurrentProfile() {
        saveSettings();
        profiles.set(selectedProfileIndex, currentInputProfile());
        persistProfiles();
        refreshAfterProfileChange(false);
    }

    private void createProfile() {
        saveCurrentProfile();
        DeviceProfile profile = new DeviceProfile(
                tr("newProfileName") + " " + (profiles.size() + 1),
                DEFAULT_HOST,
                DEFAULT_PORT,
                DEFAULT_PIN
        );
        profiles.add(profile);
        selectedProfileIndex = profiles.size() - 1;
        persistProfiles();
        refreshAfterProfileChange(false);
        setStatus(tr("profileAdded"), ACCENT);
    }

    private void deleteCurrentProfile() {
        if (profiles.size() <= 1) {
            fillProfile(new DeviceProfile(tr("defaultProfileName"), DEFAULT_HOST, DEFAULT_PORT, DEFAULT_PIN));
            saveCurrentProfile();
            setStatus(tr("profileCleared"), WARN);
            return;
        }

        profiles.remove(selectedProfileIndex);
        selectedProfileIndex = Math.max(0, selectedProfileIndex - 1);
        persistProfiles();
        refreshAfterProfileChange(false);
        setStatus(tr("profileDeleted"), DANGER);
    }

    private void refreshAfterProfileChange(boolean animate) {
        rebuildContent(animate);
    }

    private EditText labeledInput(LinearLayout parent, String label, String hint, String value) {
        TextView labelView = text(label, 13, labelColor(), Typeface.BOLD);
        labelView.setPadding(dp(2), 0, dp(2), dp(6));
        parent.addView(labelView);

        EditText edit = new EditText(this);
        edit.setHint(hint);
        edit.setText(value);
        edit.setSingleLine(true);
        edit.setTextColor(TEXT);
        edit.setHintTextColor(lightTheme ? Color.rgb(136, 146, 164) : Color.rgb(111, 121, 130));
        edit.setTextSize(16);
        edit.setPadding(dp(14), 0, dp(14), 0);
        edit.setBackground(panelBg(fieldBg(), subtleStroke(), 8));
        parent.addView(edit, inputParams());
        return edit;
    }

    private LinearLayout.LayoutParams inputParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(52)
        );
        params.setMargins(0, 0, 0, dp(12));
        return params;
    }

    private TextView actionButton(String title, String subtitle, int bgColor, int textColor) {
        return commandLikeButton(title, subtitle, bgColor, textColor, 58);
    }

    private TextView commandLikeButton(String title, String subtitle, int bgColor, int textColor, int height) {
        TextView button = new TextView(this);
        button.setText(title + "\n" + subtitle);
        button.setTextColor(textColor);
        button.setTextSize(15);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setGravity(Gravity.CENTER_VERTICAL);
        button.setIncludeFontPadding(false);
        button.setLineSpacing(dp(3), 1.0f);
        button.setPadding(dp(14), 0, dp(14), 0);
        button.setBackground(panelBg(bgColor, softenStroke(bgColor), 8));
        button.setClickable(true);
        button.setFocusable(true);

        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                dp(height)
        );
        params.setMargins(0, dp(8), 0, 0);
        button.setLayoutParams(params);
        return button;
    }

    private void addCommandButton(GridLayout grid, String title, String command, boolean confirm, int bgColor, int span, int iconRes) {
        LinearLayout button = vertical();
        button.setGravity(Gravity.CENTER);
        button.setPadding(dp(12), dp(10), dp(12), dp(10));
        button.setBackground(panelBg(bgColor, softenStroke(bgColor), 8));
        button.setClickable(true);
        button.setFocusable(true);

        ImageView icon = new ImageView(this);
        icon.setImageResource(iconRes);
        icon.setColorFilter(TEXT);
        icon.setScaleType(ImageView.ScaleType.CENTER);
        button.addView(icon, new LinearLayout.LayoutParams(dp(30), dp(30)));

        TextView label = text(title, 12, TEXT, Typeface.BOLD);
        label.setGravity(Gravity.CENTER);
        label.setPadding(0, dp(8), 0, 0);
        button.addView(label, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        ));

        GridLayout.LayoutParams params = new GridLayout.LayoutParams();
        params.width = 0;
        params.height = dp(86);
        params.columnSpec = GridLayout.spec(GridLayout.UNDEFINED, span, 1f);
        params.setMargins(dp(4), dp(4), dp(4), dp(4));
        button.setLayoutParams(params);

        button.setOnClickListener(v -> {
            animateTap(v);
            saveSettings();
            hideKeyboard();
            if (confirm) {
                new AlertDialog.Builder(this)
                        .setTitle(title)
                        .setMessage(tr("confirmMessage"))
                        .setNegativeButton(tr("cancel"), null)
                        .setPositiveButton(tr("send"), (dialog, which) -> runRequest("command", command))
                        .show();
            } else {
                runRequest("command", command);
            }
        });

        grid.addView(button);
    }

    private void saveSettings() {
        if (hostInput == null || portInput == null || pinInput == null) {
            return;
        }
        prefs.edit()
                .putString("host", hostInput.getText().toString().trim())
                .putString("port", portInput.getText().toString().trim())
                .putString("pin", pinInput.getText().toString().trim())
                .apply();
    }

    private void runRequest(String type, String command) {
        setStatus(tr("sending"), WARN);
        new Thread(() -> {
            try {
                String response = type.equals("health")
                        ? getHealth()
                        : postCommand(command);
                setStatus(response, ACCENT);
            } catch (Exception e) {
                setStatus(tr("errorPrefix") + e.getMessage(), DANGER);
            }
        }).start();
    }

    private String baseUrl() {
        DeviceProfile profile = activeProfile();
        String host = profile.host;
        String port = profile.port;
        if (host == null || host.isEmpty()) host = DEFAULT_HOST;
        if (port == null || port.isEmpty()) port = DEFAULT_PORT;
        if (host.startsWith("http://") || host.startsWith("https://")) {
            while (host.endsWith("/")) {
                host = host.substring(0, host.length() - 1);
            }
            return host;
        }
        return "http://" + host + ":" + port;
    }

    private String getHealth() throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(baseUrl() + "/health").openConnection();
        conn.setConnectTimeout(4000);
        conn.setReadTimeout(4000);
        conn.setRequestMethod("GET");
        int code = conn.getResponseCode();
        String body = read(conn);
        return code == 200 ? tr("connectionOk") : "HTTP " + code + ": " + body;
    }

    private String postCommand(String command) throws Exception {
        login();

        HttpURLConnection conn = (HttpURLConnection) new URL(baseUrl() + "/api/command").openConnection();
        conn.setConnectTimeout(4000);
        conn.setReadTimeout(4000);
        conn.setRequestMethod("POST");
        conn.setRequestProperty("Content-Type", "application/json");
        if (sessionCookie != null) {
            conn.setRequestProperty("Cookie", sessionCookie);
        }
        conn.setDoOutput(true);

        String json = "{\"command\":\"" + command + "\"}";
        try (OutputStream out = conn.getOutputStream()) {
            out.write(json.getBytes(StandardCharsets.UTF_8));
        }

        int code = conn.getResponseCode();
        String body = read(conn);
        if (code >= 200 && code < 300) {
            return labelFor(command) + " " + tr("sentSuffix");
        }
        return "HTTP " + code + ": " + body;
    }

    private void login() throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(baseUrl() + "/login").openConnection();
        conn.setInstanceFollowRedirects(false);
        conn.setConnectTimeout(4000);
        conn.setReadTimeout(4000);
        conn.setRequestMethod("POST");
        conn.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
        conn.setDoOutput(true);

        String pin = activeProfile().pin;
        String body = "pin=" + (pin == null ? "" : pin);
        try (OutputStream out = conn.getOutputStream()) {
            out.write(body.getBytes(StandardCharsets.UTF_8));
        }

        int code = conn.getResponseCode();
        String cookie = conn.getHeaderField("Set-Cookie");
        if ((code == 303 || code == 302) && cookie != null) {
            sessionCookie = cookie.split(";", 2)[0];
            return;
        }

        throw new IllegalStateException(tr("loginFailed"));
    }

    private String read(HttpURLConnection conn) throws Exception {
        InputStream stream = conn.getResponseCode() >= 400 ? conn.getErrorStream() : conn.getInputStream();
        if (stream == null) {
            return "";
        }
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            StringBuilder builder = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                builder.append(line);
            }
            return builder.toString();
        }
    }

    private void setStatus(String text, int color) {
        ui.post(() -> {
            statusView.setText(text);
            statusDot.setBackground(ovalBg(color));
            ObjectAnimator pulseX = ObjectAnimator.ofFloat(statusDot, "scaleX", 1f, 1.45f, 1f);
            ObjectAnimator pulseY = ObjectAnimator.ofFloat(statusDot, "scaleY", 1f, 1.45f, 1f);
            AnimatorSet set = new AnimatorSet();
            set.playTogether(pulseX, pulseY);
            set.setDuration(360);
            set.setInterpolator(new DecelerateInterpolator());
            set.start();
        });
    }

    private void animateScreen(View content) {
        content.setAlpha(0f);
        content.setTranslationY(dp(14));
        content.animate()
                .alpha(1f)
                .translationY(0f)
                .setDuration(420)
                .setInterpolator(new DecelerateInterpolator())
                .start();
    }

    private void animateTap(View view) {
        view.animate()
                .scaleX(0.97f)
                .scaleY(0.97f)
                .setDuration(80)
                .withEndAction(() -> view.animate().scaleX(1f).scaleY(1f).setDuration(140).start())
                .start();
    }

    private LinearLayout vertical() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        return layout;
    }

    private LinearLayout horizontal() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.HORIZONTAL);
        return layout;
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
        );
    }

    private TextView text(String value, int sp, int color, int style) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextColor(color);
        view.setTextSize(sp);
        view.setTypeface(Typeface.DEFAULT, style);
        return view;
    }

    private GradientDrawable panelBg(int color, int stroke, int radius) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radius));
        drawable.setStroke(dp(1), stroke);
        return drawable;
    }

    private GradientDrawable gradientBg(int start, int end, int stroke, int radius) {
        GradientDrawable drawable = new GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                new int[]{start, end}
        );
        drawable.setCornerRadius(dp(radius));
        drawable.setStroke(dp(1), stroke);
        return drawable;
    }

    private GradientDrawable ovalBg(int color) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setShape(GradientDrawable.OVAL);
        drawable.setColor(color);
        return drawable;
    }

    private int brighten(int color) {
        int red = Math.min(255, Color.red(color) + 22);
        int green = Math.min(255, Color.green(color) + 22);
        int blue = Math.min(255, Color.blue(color) + 22);
        return Color.rgb(red, green, blue);
    }

    private int softenStroke(int color) {
        int red = Math.min(255, Color.red(color) + 34);
        int green = Math.min(255, Color.green(color) + 28);
        int blue = Math.min(255, Color.blue(color) + 46);
        return Color.rgb(red, green, blue);
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density + 0.5f);
    }

    private String lang() {
        return prefs.getString("lang", "ru");
    }

    private int languageIndex(String code) {
        for (int i = 0; i < LANG_CODES.length; i++) {
            if (LANG_CODES[i].equals(code)) {
                return i;
            }
        }
        return 1;
    }

    private String labelFor(String command) {
        if ("mute".equals(command)) return tr("muteTitle");
        if ("lock".equals(command)) return tr("lockTitle");
        if ("sleep".equals(command)) return tr("sleepTitle");
        if ("restart".equals(command)) return tr("restartTitle");
        if ("shutdown".equals(command)) return tr("shutdownTitle");
        return tr("command");
    }

    private void hideKeyboard() {
        InputMethodManager manager = (InputMethodManager) getSystemService(Context.INPUT_METHOD_SERVICE);
        View focused = getCurrentFocus();
        if (manager != null && focused != null) {
            manager.hideSoftInputFromWindow(focused.getWindowToken(), 0);
        }
    }

    private String tr(String key) {
        Map<String, String> dictionary = dictionaries().get(lang());
        if (dictionary == null || !dictionary.containsKey(key)) {
            dictionary = dictionaries().get("en");
        }
        String value = dictionary.get(key);
        return value == null ? key : value;
    }

    private Map<String, Map<String, String>> dictionaries() {
        Map<String, Map<String, String>> all = new HashMap<>();
        all.put("en", dict(
                "eyebrow", "Local remote",
                "subtitle", "Control your PC from your phone: sound, lock, sleep, restart and shutdown.",
                "ready", "Ready. Check IP, port and PIN, then test the connection.",
                "languageTitle", "Language",
                "languageSubtitle", "Choose the app language. The setting is saved on this phone.",
                "languageLabel", "App language",
                "languageSaved", "Language saved.",
                "themeTitle", "Theme",
                "themeSubtitle", "Switch between the premium dark look and a bright clean interface.",
                "themeDark", "Dark",
                "themeLight", "Light",
                "profilesTitle", "Devices",
                "profilesSubtitle", "Add several PCs or relay servers, then pick the device before using the remote.",
                "profileSelectLabel", "Selected device",
                "profileNameLabel", "Device name",
                "profileNameHint", "Example: Home PC",
                "defaultProfileName", "My PC",
                "newProfileName", "New device",
                "saveProfileTitle", "Save device",
                "saveProfileSub", "Update this profile",
                "addProfileTitle", "Add",
                "addProfileSub", "New device",
                "deleteProfileTitle", "Delete",
                "deleteProfileSub", "Remove device",
                "profileSaved", "Device profile saved.",
                "profileAdded", "Device profile added.",
                "profileDeleted", "Device profile deleted.",
                "profileCleared", "Device profile cleared.",
                "profileSelected", "Device selected.",
                "selectedDeviceTitle", "Selected device",
                "selectedDeviceSubtitle", "Commands will be sent to this profile.",
                "switchDeviceTitle", "Switch device",
                "switchDeviceSub", "Open device profiles",
                "tabRemote", "Remote",
                "tabDevices", "Devices",
                "tabSettings", "Settings",
                "settingsTitle", "Connection settings",
                "settingsSubtitle", "These values must match the server running on your PC.",
                "hostLabel", "PC IP address",
                "hostHint", "Example: 192.168.1.25",
                "portLabel", "Port",
                "portHint", "Usually 8765",
                "pinHint", "Server access code",
                "saveTitle", "Save settings",
                "saveSub", "Remember IP, port and PIN",
                "testTitle", "Test connection",
                "testSub", "Check that the PC server responds",
                "controlsTitle", "PC controls",
                "controlsSubtitle", "Commands are sent to the PC on your local network.",
                "muteTitle", "Sound",
                "muteSub", "Toggle mute",
                "lockTitle", "Lock",
                "lockSub", "Lock the desktop",
                "sleepTitle", "Sleep",
                "sleepSub", "Put the PC to sleep",
                "restartTitle", "Restart",
                "restartSub", "Restart immediately",
                "shutdownTitle", "Shutdown",
                "shutdownSub", "Turn off completely",
                "note", "Important: the app works when the PC and phone are on the same network and the PC server is running.",
                "confirmMessage", "Send this command to the PC?",
                "cancel", "Cancel",
                "send", "Send",
                "sending", "Sending request...",
                "settingsSaved", "Settings saved.",
                "connectionOk", "Connection works.",
                "errorPrefix", "Error: ",
                "sentSuffix", "sent.",
                "loginFailed", "wrong PIN or server rejected the request",
                "command", "Command"
        ));
        all.put("ru", dict(
                "eyebrow", "\u041b\u043e\u043a\u0430\u043b\u044c\u043d\u044b\u0439 \u043f\u0443\u043b\u044c\u0442",
                "subtitle", "\u0423\u043f\u0440\u0430\u0432\u043b\u044f\u0439 \u043a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440\u043e\u043c \u0441 \u0442\u0435\u043b\u0435\u0444\u043e\u043d\u0430: \u0437\u0432\u0443\u043a, \u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u043a\u0430, \u0441\u043e\u043d, \u043f\u0435\u0440\u0435\u0437\u0430\u043f\u0443\u0441\u043a \u0438 \u0432\u044b\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435.",
                "ready", "\u0413\u043e\u0442\u043e\u0432\u043e. \u041f\u0440\u043e\u0432\u0435\u0440\u044c IP, \u043f\u043e\u0440\u0442 \u0438 PIN, \u043f\u043e\u0442\u043e\u043c \u043d\u0430\u0436\u043c\u0438 \u0442\u0435\u0441\u0442 \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u044f.",
                "languageTitle", "\u042f\u0437\u044b\u043a",
                "languageSubtitle", "\u0412\u044b\u0431\u0435\u0440\u0438 \u044f\u0437\u044b\u043a \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u044f. \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430 \u0441\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u0441\u044f \u043d\u0430 \u044d\u0442\u043e\u043c \u0442\u0435\u043b\u0435\u0444\u043e\u043d\u0435.",
                "languageLabel", "\u042f\u0437\u044b\u043a \u0438\u043d\u0442\u0435\u0440\u0444\u0435\u0439\u0441\u0430",
                "languageSaved", "\u042f\u0437\u044b\u043a \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d.",
                "themeTitle", "\u0422\u0435\u043c\u0430",
                "themeSubtitle", "\u041f\u0435\u0440\u0435\u043a\u043b\u044e\u0447\u0430\u0439 \u0442\u0435\u043c\u043d\u044b\u0439 \u043f\u0440\u0435\u043c\u0438\u0430\u043b\u044c\u043d\u044b\u0439 \u0441\u0442\u0438\u043b\u044c \u0438 \u0441\u0432\u0435\u0442\u043b\u044b\u0439 \u0447\u0438\u0441\u0442\u044b\u0439 \u0438\u043d\u0442\u0435\u0440\u0444\u0435\u0439\u0441.",
                "themeDark", "\u0422\u0435\u043c\u043d\u0430\u044f",
                "themeLight", "\u0421\u0432\u0435\u0442\u043b\u0430\u044f",
                "profilesTitle", "\u0423\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u0430",
                "profilesSubtitle", "\u0414\u043e\u0431\u0430\u0432\u043b\u044f\u0439 \u043d\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u043e \u041f\u041a \u0438\u043b\u0438 relay-\u0441\u0435\u0440\u0432\u0435\u0440\u043e\u0432, \u0430 \u043f\u0435\u0440\u0435\u0434 \u043f\u0443\u043b\u044c\u0442\u043e\u043c \u0432\u044b\u0431\u0438\u0440\u0430\u0439 \u043d\u0443\u0436\u043d\u043e\u0435 \u0443\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u043e.",
                "profileSelectLabel", "\u0412\u044b\u0431\u0440\u0430\u043d\u043d\u043e\u0435 \u0443\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u043e",
                "profileNameLabel", "\u0418\u043c\u044f \u0443\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u0430",
                "profileNameHint", "\u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: \u0414\u043e\u043c\u0430\u0448\u043d\u0438\u0439 \u041f\u041a",
                "defaultProfileName", "\u041c\u043e\u0439 \u041f\u041a",
                "newProfileName", "\u041d\u043e\u0432\u043e\u0435 \u0443\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u043e",
                "saveProfileTitle", "\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0443\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u043e",
                "saveProfileSub", "\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u044d\u0442\u043e\u0442 \u043f\u0440\u043e\u0444\u0438\u043b\u044c",
                "addProfileTitle", "\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c",
                "addProfileSub", "\u041d\u043e\u0432\u044b\u0439 \u041f\u041a",
                "deleteProfileTitle", "\u0423\u0434\u0430\u043b\u0438\u0442\u044c",
                "deleteProfileSub", "\u0423\u0431\u0440\u0430\u0442\u044c \u043f\u0440\u043e\u0444\u0438\u043b\u044c",
                "profileSaved", "\u041f\u0440\u043e\u0444\u0438\u043b\u044c \u0443\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u0430 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d.",
                "profileAdded", "\u041f\u0440\u043e\u0444\u0438\u043b\u044c \u0434\u043e\u0431\u0430\u0432\u043b\u0435\u043d.",
                "profileDeleted", "\u041f\u0440\u043e\u0444\u0438\u043b\u044c \u0443\u0434\u0430\u043b\u0435\u043d.",
                "profileCleared", "\u041f\u0440\u043e\u0444\u0438\u043b\u044c \u043e\u0447\u0438\u0449\u0435\u043d.",
                "profileSelected", "\u0423\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u043e \u0432\u044b\u0431\u0440\u0430\u043d\u043e.",
                "selectedDeviceTitle", "\u0412\u044b\u0431\u0440\u0430\u043d\u043d\u044b\u0439 \u041f\u041a",
                "selectedDeviceSubtitle", "\u041a\u043e\u043c\u0430\u043d\u0434\u044b \u0431\u0443\u0434\u0443\u0442 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u044f\u0442\u044c\u0441\u044f \u0432 \u044d\u0442\u043e\u0442 \u043f\u0440\u043e\u0444\u0438\u043b\u044c.",
                "switchDeviceTitle", "\u0421\u043c\u0435\u043d\u0438\u0442\u044c \u041f\u041a",
                "switchDeviceSub", "\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043f\u0440\u043e\u0444\u0438\u043b\u0438",
                "tabRemote", "\u041f\u0443\u043b\u044c\u0442",
                "tabDevices", "\u041f\u041a",
                "tabSettings", "\u0415\u0449\u0435",
                "settingsTitle", "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u044f",
                "settingsSubtitle", "\u042d\u0442\u0438 \u0434\u0430\u043d\u043d\u044b\u0435 \u0434\u043e\u043b\u0436\u043d\u044b \u0441\u043e\u0432\u043f\u0430\u0434\u0430\u0442\u044c \u0441 \u0441\u0435\u0440\u0432\u0435\u0440\u043e\u043c \u043d\u0430 \u043a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440\u0435.",
                "hostLabel", "IP \u043a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440\u0430",
                "hostHint", "\u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: 192.168.1.25",
                "portLabel", "\u041f\u043e\u0440\u0442",
                "portHint", "\u041e\u0431\u044b\u0447\u043d\u043e 8765",
                "pinHint", "\u041a\u043e\u0434 \u0434\u043e\u0441\u0442\u0443\u043f\u0430 \u043a \u0441\u0435\u0440\u0432\u0435\u0440\u0443",
                "saveTitle", "\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438",
                "saveSub", "\u0417\u0430\u043f\u043e\u043c\u043d\u0438\u0442\u044c IP, \u043f\u043e\u0440\u0442 \u0438 PIN",
                "testTitle", "\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435",
                "testSub", "\u0423\u0431\u0435\u0434\u0438\u0442\u044c\u0441\u044f, \u0447\u0442\u043e \u0441\u0435\u0440\u0432\u0435\u0440 \u043d\u0430 \u041f\u041a \u043e\u0442\u0432\u0435\u0447\u0430\u0435\u0442",
                "controlsTitle", "\u0423\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u043a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440\u043e\u043c",
                "controlsSubtitle", "\u041a\u043e\u043c\u0430\u043d\u0434\u044b \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u044f\u044e\u0442\u0441\u044f \u043d\u0430 \u041f\u041a \u0432 \u0442\u0432\u043e\u0435\u0439 \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u043e\u0439 \u0441\u0435\u0442\u0438.",
                "muteTitle", "\u0417\u0432\u0443\u043a",
                "muteSub", "\u0412\u043a\u043b/\u0432\u044b\u043a\u043b \u0437\u0432\u0443\u043a",
                "lockTitle", "\u0411\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u043a\u0430",
                "lockSub", "\u0417\u0430\u043a\u0440\u044b\u0442\u044c \u0440\u0430\u0431\u043e\u0447\u0438\u0439 \u0441\u0442\u043e\u043b",
                "sleepTitle", "\u0421\u043e\u043d",
                "sleepSub", "\u041e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c \u041f\u041a \u0441\u043f\u0430\u0442\u044c",
                "restartTitle", "\u041f\u0435\u0440\u0435\u0437\u0430\u043f\u0443\u0441\u043a",
                "restartSub", "\u0421\u0440\u0430\u0437\u0443 \u043f\u0435\u0440\u0435\u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c",
                "shutdownTitle", "\u0412\u044b\u043a\u043b\u044e\u0447\u0438\u0442\u044c",
                "shutdownSub", "\u041f\u043e\u043b\u043d\u043e\u0435 \u0432\u044b\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435",
                "note", "\u0412\u0430\u0436\u043d\u043e: \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442, \u043a\u043e\u0433\u0434\u0430 \u043a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440 \u0438 \u0442\u0435\u043b\u0435\u0444\u043e\u043d \u0432 \u043e\u0434\u043d\u043e\u0439 \u0441\u0435\u0442\u0438, \u0430 \u0441\u0435\u0440\u0432\u0435\u0440 \u043d\u0430 \u041f\u041a \u0437\u0430\u043f\u0443\u0449\u0435\u043d.",
                "confirmMessage", "\u041e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c \u043a\u043e\u043c\u0430\u043d\u0434\u0443 \u043d\u0430 \u043a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440?",
                "cancel", "\u041e\u0442\u043c\u0435\u043d\u0430",
                "send", "\u041e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c",
                "sending", "\u041e\u0442\u043f\u0440\u0430\u0432\u043b\u044f\u044e \u0437\u0430\u043f\u0440\u043e\u0441...",
                "settingsSaved", "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u044b.",
                "connectionOk", "\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442.",
                "errorPrefix", "\u041e\u0448\u0438\u0431\u043a\u0430: ",
                "sentSuffix", "\u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e.",
                "loginFailed", "\u043d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 PIN \u0438\u043b\u0438 \u0441\u0435\u0440\u0432\u0435\u0440 \u043d\u0435 \u043f\u0443\u0441\u0442\u0438\u043b",
                "command", "\u041a\u043e\u043c\u0430\u043d\u0434\u0430"
        ));
        all.put("uk", translatedFromRu("uk"));
        all.put("sk", translatedFromRu("sk"));
        all.put("cs", translatedFromRu("cs"));
        all.put("ja", translatedFromRu("ja"));
        all.put("de", translatedFromRu("de"));
        all.put("es", translatedFromRu("es"));
        all.put("fr", translatedFromRu("fr"));
        all.put("pl", translatedFromRu("pl"));
        return all;
    }

    private Map<String, String> translatedFromRu(String code) {
        if ("uk".equals(code)) {
            return dict(
                    "eyebrow", "\u041b\u043e\u043a\u0430\u043b\u044c\u043d\u0438\u0439 \u043f\u0443\u043b\u044c\u0442",
                    "subtitle", "\u041a\u0435\u0440\u0443\u0439 \u043a\u043e\u043c\u043f'\u044e\u0442\u0435\u0440\u043e\u043c \u0437 \u0442\u0435\u043b\u0435\u0444\u043e\u043d\u0430: \u0437\u0432\u0443\u043a, \u0431\u043b\u043e\u043a\u0443\u0432\u0430\u043d\u043d\u044f, \u0441\u043e\u043d, \u043f\u0435\u0440\u0435\u0437\u0430\u043f\u0443\u0441\u043a \u0456 \u0432\u0438\u043c\u043a\u043d\u0435\u043d\u043d\u044f.",
                    "ready", "\u0413\u043e\u0442\u043e\u0432\u043e. \u041f\u0435\u0440\u0435\u0432\u0456\u0440 IP, \u043f\u043e\u0440\u0442 \u0456 PIN, \u043f\u043e\u0442\u0456\u043c \u043d\u0430\u0442\u0438\u0441\u043d\u0438 \u0442\u0435\u0441\u0442 \u043f\u0456\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u043d\u044f.",
                    "languageTitle", "\u041c\u043e\u0432\u0430", "languageSubtitle", "\u041e\u0431\u0435\u0440\u0438 \u043c\u043e\u0432\u0443 \u0434\u043e\u0434\u0430\u0442\u043a\u0430. \u041d\u0430\u043b\u0430\u0448\u0442\u0443\u0432\u0430\u043d\u043d\u044f \u0437\u0431\u0435\u0440\u0435\u0436\u0435\u0442\u044c\u0441\u044f \u043d\u0430 \u0446\u044c\u043e\u043c\u0443 \u0442\u0435\u043b\u0435\u0444\u043e\u043d\u0456.", "languageLabel", "\u041c\u043e\u0432\u0430 \u0456\u043d\u0442\u0435\u0440\u0444\u0435\u0439\u0441\u0443", "languageSaved", "\u041c\u043e\u0432\u0443 \u0437\u0431\u0435\u0440\u0435\u0436\u0435\u043d\u043e.",
                    "settingsTitle", "\u041d\u0430\u043b\u0430\u0448\u0442\u0443\u0432\u0430\u043d\u043d\u044f \u043f\u0456\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u043d\u044f", "settingsSubtitle", "\u0426\u0456 \u0434\u0430\u043d\u0456 \u043c\u0430\u044e\u0442\u044c \u0437\u0431\u0456\u0433\u0430\u0442\u0438\u0441\u044f \u0437 \u0441\u0435\u0440\u0432\u0435\u0440\u043e\u043c \u043d\u0430 \u043a\u043e\u043c\u043f'\u044e\u0442\u0435\u0440\u0456.",
                    "hostLabel", "IP \u043a\u043e\u043c\u043f'\u044e\u0442\u0435\u0440\u0430", "hostHint", "\u041f\u0440\u0438\u043a\u043b\u0430\u0434: 192.168.1.25", "portLabel", "\u041f\u043e\u0440\u0442", "portHint", "\u0417\u0430\u0437\u0432\u0438\u0447\u0430\u0439 8765", "pinHint", "\u041a\u043e\u0434 \u0434\u043e\u0441\u0442\u0443\u043f\u0443 \u0434\u043e \u0441\u0435\u0440\u0432\u0435\u0440\u0430",
                    "saveTitle", "\u0417\u0431\u0435\u0440\u0435\u0433\u0442\u0438 \u043d\u0430\u043b\u0430\u0448\u0442\u0443\u0432\u0430\u043d\u043d\u044f", "saveSub", "\u0417\u0430\u043f\u0430\u043c'\u044f\u0442\u0430\u0442\u0438 IP, \u043f\u043e\u0440\u0442 \u0456 PIN", "testTitle", "\u041f\u0435\u0440\u0435\u0432\u0456\u0440\u0438\u0442\u0438 \u043f\u0456\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u043d\u044f", "testSub", "\u041f\u0435\u0440\u0435\u043a\u043e\u043d\u0430\u0442\u0438\u0441\u044f, \u0449\u043e \u0441\u0435\u0440\u0432\u0435\u0440 \u043d\u0430 \u041f\u041a \u0432\u0456\u0434\u043f\u043e\u0432\u0456\u0434\u0430\u0454",
                    "controlsTitle", "\u041a\u0435\u0440\u0443\u0432\u0430\u043d\u043d\u044f \u043a\u043e\u043c\u043f'\u044e\u0442\u0435\u0440\u043e\u043c", "controlsSubtitle", "\u041a\u043e\u043c\u0430\u043d\u0434\u0438 \u043d\u0430\u0434\u0441\u0438\u043b\u0430\u044e\u0442\u044c\u0441\u044f \u043d\u0430 \u041f\u041a \u0443 \u0442\u0432\u043e\u0457\u0439 \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u0456\u0439 \u043c\u0435\u0440\u0435\u0436\u0456.",
                    "muteTitle", "\u0417\u0432\u0443\u043a", "muteSub", "\u0423\u0432\u0456\u043c\u043a/\u0432\u0438\u043c\u043a \u0437\u0432\u0443\u043a", "lockTitle", "\u0411\u043b\u043e\u043a\u0443\u0432\u0430\u043d\u043d\u044f", "lockSub", "\u0417\u0430\u043a\u0440\u0438\u0442\u0438 \u0440\u043e\u0431\u043e\u0447\u0438\u0439 \u0441\u0442\u0456\u043b", "sleepTitle", "\u0421\u043e\u043d", "sleepSub", "\u041f\u0435\u0440\u0435\u0432\u0435\u0441\u0442\u0438 \u041f\u041a \u0443 \u0441\u043e\u043d", "restartTitle", "\u041f\u0435\u0440\u0435\u0437\u0430\u043f\u0443\u0441\u043a", "restartSub", "\u041e\u0434\u0440\u0430\u0437\u0443 \u043f\u0435\u0440\u0435\u0437\u0430\u0432\u0430\u043d\u0442\u0430\u0436\u0438\u0442\u0438", "shutdownTitle", "\u0412\u0438\u043c\u043a\u043d\u0443\u0442\u0438", "shutdownSub", "\u041f\u043e\u0432\u043d\u0435 \u0432\u0438\u043c\u043a\u043d\u0435\u043d\u043d\u044f",
                    "note", "\u0412\u0430\u0436\u043b\u0438\u0432\u043e: \u0434\u043e\u0434\u0430\u0442\u043e\u043a \u043f\u0440\u0430\u0446\u044e\u0454, \u043a\u043e\u043b\u0438 \u041f\u041a \u0456 \u0442\u0435\u043b\u0435\u0444\u043e\u043d \u0432 \u043e\u0434\u043d\u0456\u0439 \u043c\u0435\u0440\u0435\u0436\u0456, \u0430 \u0441\u0435\u0440\u0432\u0435\u0440 \u043d\u0430 \u041f\u041a \u0437\u0430\u043f\u0443\u0449\u0435\u043d\u0438\u0439.", "confirmMessage", "\u041d\u0430\u0434\u0456\u0441\u043b\u0430\u0442\u0438 \u0446\u044e \u043a\u043e\u043c\u0430\u043d\u0434\u0443 \u043d\u0430 \u043a\u043e\u043c\u043f'\u044e\u0442\u0435\u0440?", "cancel", "\u0421\u043a\u0430\u0441\u0443\u0432\u0430\u0442\u0438", "send", "\u041d\u0430\u0434\u0456\u0441\u043b\u0430\u0442\u0438", "sending", "\u041d\u0430\u0434\u0441\u0438\u043b\u0430\u044e \u0437\u0430\u043f\u0438\u0442...", "settingsSaved", "\u041d\u0430\u043b\u0430\u0448\u0442\u0443\u0432\u0430\u043d\u043d\u044f \u0437\u0431\u0435\u0440\u0435\u0436\u0435\u043d\u043e.", "connectionOk", "\u041f\u0456\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u043d\u044f \u043f\u0440\u0430\u0446\u044e\u0454.", "errorPrefix", "\u041f\u043e\u043c\u0438\u043b\u043a\u0430: ", "sentSuffix", "\u043d\u0430\u0434\u0456\u0441\u043b\u0430\u043d\u043e.", "loginFailed", "\u043d\u0435\u0432\u0456\u0440\u043d\u0438\u0439 PIN \u0430\u0431\u043e \u0441\u0435\u0440\u0432\u0435\u0440 \u0432\u0456\u0434\u0445\u0438\u043b\u0438\u0432 \u0437\u0430\u043f\u0438\u0442", "command", "\u041a\u043e\u043c\u0430\u043d\u0434\u0430"
            );
        }
        if ("ja".equals(code)) {
            return dict("eyebrow", "\u30ed\u30fc\u30ab\u30eb\u30ea\u30e2\u30b3\u30f3", "subtitle", "\u30b9\u30de\u30db\u304b\u3089PC\u3092\u64cd\u4f5c: \u97f3\u91cf\u3001\u30ed\u30c3\u30af\u3001\u30b9\u30ea\u30fc\u30d7\u3001\u518d\u8d77\u52d5\u3001\u30b7\u30e3\u30c3\u30c8\u30c0\u30a6\u30f3\u3002", "ready", "\u6e96\u5099\u5b8c\u4e86\u3002IP\u3001\u30dd\u30fc\u30c8\u3001PIN\u3092\u78ba\u8a8d\u3057\u3001\u63a5\u7d9a\u3092\u30c6\u30b9\u30c8\u3057\u3066\u304f\u3060\u3055\u3044\u3002", "languageTitle", "\u8a00\u8a9e", "languageSubtitle", "\u30a2\u30d7\u30ea\u306e\u8a00\u8a9e\u3092\u9078\u629e\u3057\u307e\u3059\u3002\u8a2d\u5b9a\u306f\u3053\u306e\u30b9\u30de\u30db\u306b\u4fdd\u5b58\u3055\u308c\u307e\u3059\u3002", "languageLabel", "\u30a2\u30d7\u30ea\u306e\u8a00\u8a9e", "languageSaved", "\u8a00\u8a9e\u3092\u4fdd\u5b58\u3057\u307e\u3057\u305f\u3002", "settingsTitle", "\u63a5\u7d9a\u8a2d\u5b9a", "settingsSubtitle", "\u3053\u306e\u5024\u306fPC\u4e0a\u306e\u30b5\u30fc\u30d0\u30fc\u3068\u4e00\u81f4\u3059\u308b\u5fc5\u8981\u304c\u3042\u308a\u307e\u3059\u3002", "hostLabel", "PC\u306eIP\u30a2\u30c9\u30ec\u30b9", "hostHint", "\u4f8b: 192.168.1.25", "portLabel", "\u30dd\u30fc\u30c8", "portHint", "\u901a\u5e38 8765", "pinHint", "\u30b5\u30fc\u30d0\u30fc\u306e\u30a2\u30af\u30bb\u30b9\u30b3\u30fc\u30c9", "saveTitle", "\u8a2d\u5b9a\u3092\u4fdd\u5b58", "saveSub", "IP\u3001\u30dd\u30fc\u30c8\u3001PIN\u3092\u4fdd\u5b58", "testTitle", "\u63a5\u7d9a\u30c6\u30b9\u30c8", "testSub", "PC\u30b5\u30fc\u30d0\u30fc\u306e\u5fdc\u7b54\u3092\u78ba\u8a8d", "controlsTitle", "PC\u64cd\u4f5c", "controlsSubtitle", "\u30b3\u30de\u30f3\u30c9\u306f\u30ed\u30fc\u30ab\u30eb\u30cd\u30c3\u30c8\u30ef\u30fc\u30af\u4e0a\u306ePC\u306b\u9001\u4fe1\u3055\u308c\u307e\u3059\u3002", "muteTitle", "\u97f3\u91cf", "muteSub", "\u30df\u30e5\u30fc\u30c8\u5207\u66ff", "lockTitle", "\u30ed\u30c3\u30af", "lockSub", "\u30c7\u30b9\u30af\u30c8\u30c3\u30d7\u3092\u30ed\u30c3\u30af", "sleepTitle", "\u30b9\u30ea\u30fc\u30d7", "sleepSub", "PC\u3092\u30b9\u30ea\u30fc\u30d7", "restartTitle", "\u518d\u8d77\u52d5", "restartSub", "\u3059\u3050\u306b\u518d\u8d77\u52d5", "shutdownTitle", "\u30b7\u30e3\u30c3\u30c8\u30c0\u30a6\u30f3", "shutdownSub", "\u5b8c\u5168\u306b\u96fb\u6e90\u30aa\u30d5", "note", "\u91cd\u8981: PC\u3068\u30b9\u30de\u30db\u304c\u540c\u3058\u30cd\u30c3\u30c8\u30ef\u30fc\u30af\u306b\u3042\u308a\u3001PC\u30b5\u30fc\u30d0\u30fc\u304c\u8d77\u52d5\u4e2d\u306e\u5834\u5408\u306b\u52d5\u4f5c\u3057\u307e\u3059\u3002", "confirmMessage", "\u3053\u306e\u30b3\u30de\u30f3\u30c9\u3092PC\u306b\u9001\u4fe1\u3057\u307e\u3059\u304b?", "cancel", "\u30ad\u30e3\u30f3\u30bb\u30eb", "send", "\u9001\u4fe1", "sending", "\u9001\u4fe1\u4e2d...", "settingsSaved", "\u8a2d\u5b9a\u3092\u4fdd\u5b58\u3057\u307e\u3057\u305f\u3002", "connectionOk", "\u63a5\u7d9a\u306f\u6b63\u5e38\u3067\u3059\u3002", "errorPrefix", "\u30a8\u30e9\u30fc: ", "sentSuffix", "\u9001\u4fe1\u3055\u308c\u307e\u3057\u305f\u3002", "loginFailed", "PIN\u304c\u9055\u3046\u304b\u3001\u30b5\u30fc\u30d0\u30fc\u304c\u62d2\u5426\u3057\u307e\u3057\u305f", "command", "\u30b3\u30de\u30f3\u30c9");
        }
        if ("sk".equals(code)) return latin("Miestny ovladac", "Ovladaj PC z telefonu: zvuk, zamok, spanok, restart a vypnutie.", "Pripravene. Skontroluj IP, port a PIN, potom otestuj pripojenie.", "Jazyk", "Vyber jazyk aplikacie. Nastavenie sa ulozi v tomto telefone.", "Jazyk aplikacie", "Jazyk ulozeny.", "Nastavenia pripojenia", "Tieto hodnoty sa musia zhodovat so serverom na PC.", "IP adresa PC", "Priklad: 192.168.1.25", "Port", "Zvycajne 8765", "Pristupovy kod servera", "Ulozit nastavenia", "Zapamatat IP, port a PIN", "Test pripojenia", "Overit, ze PC server odpoveda", "Ovlada\u010de PC", "Prikazy sa odosielaju do PC v lokalnej sieti.", "Zvuk", "Zap/vyp zvuk", "Zamknut", "Zamknut plochu", "Spanok", "Uspat PC", "Restart", "Restartovat hned", "Vypnut", "Uplne vypnutie", "Dolezite: aplikacia funguje, ked su PC a telefon v rovnakej sieti a server na PC bezi.", "Odoslat tento prikaz do PC?", "Zrusit", "Odoslat", "Odosielam poziadavku...", "Nastavenia ulozene.", "Pripojenie funguje.", "Chyba: ", "odoslane.", "nespravny PIN alebo server odmietol poziadavku", "Prikaz");
        if ("cs".equals(code)) return latin("Mistni ovladac", "Ovladej PC z telefonu: zvuk, zamknuti, spanek, restart a vypnuti.", "Pripraveno. Zkontroluj IP, port a PIN, potom otestuj pripojeni.", "Jazyk", "Vyber jazyk aplikace. Nastaveni se ulozi v tomto telefonu.", "Jazyk aplikace", "Jazyk ulozen.", "Nastaveni pripojeni", "Tyto hodnoty se musi shodovat se serverem na PC.", "IP adresa PC", "Priklad: 192.168.1.25", "Port", "Obvykle 8765", "Pristupovy kod serveru", "Ulozit nastaveni", "Zapamatovat IP, port a PIN", "Test pripojeni", "Overit, ze PC server odpovida", "Ovlada\u010de PC", "Prikazy se odesilaji do PC v lokalni siti.", "Zvuk", "Zap/vyp zvuk", "Zamknout", "Zamknout plochu", "Spanek", "Uspat PC", "Restart", "Restartovat ihned", "Vypnout", "Uplne vypnuti", "Dulezite: aplikace funguje, kdyz jsou PC a telefon ve stejne siti a server na PC bezi.", "Odeslat tento prikaz do PC?", "Zrusit", "Odeslat", "Odesilam pozadavek...", "Nastaveni ulozeno.", "Pripojeni funguje.", "Chyba: ", "odeslano.", "spatny PIN nebo server pozadavek odmitl", "Prikaz");
        if ("de".equals(code)) return latin("Lokale Fernbedienung", "Steuere deinen PC vom Handy: Ton, Sperre, Schlafmodus, Neustart und Herunterfahren.", "Bereit. Pruefe IP, Port und PIN, dann teste die Verbindung.", "Sprache", "Waehle die App-Sprache. Die Einstellung wird auf diesem Handy gespeichert.", "App-Sprache", "Sprache gespeichert.", "Verbindungseinstellungen", "Diese Werte muessen zum Server auf deinem PC passen.", "PC-IP-Adresse", "Beispiel: 192.168.1.25", "Port", "Normalerweise 8765", "Zugriffscode des Servers", "Einstellungen speichern", "IP, Port und PIN merken", "Verbindung testen", "Pruefen, ob der PC-Server antwortet", "PC-Steuerung", "Befehle werden an den PC im lokalen Netzwerk gesendet.", "Ton", "Stumm umschalten", "Sperren", "Desktop sperren", "Schlafmodus", "PC schlafen legen", "Neustart", "Sofort neu starten", "Herunterfahren", "Komplett ausschalten", "Wichtig: Die App funktioniert, wenn PC und Handy im selben Netzwerk sind und der PC-Server laeuft.", "Diesen Befehl an den PC senden?", "Abbrechen", "Senden", "Sende Anfrage...", "Einstellungen gespeichert.", "Verbindung funktioniert.", "Fehler: ", "gesendet.", "falsche PIN oder Server hat die Anfrage abgelehnt", "Befehl");
        if ("es".equals(code)) return latin("Control local", "Controla tu PC desde el telefono: sonido, bloqueo, suspension, reinicio y apagado.", "Listo. Revisa IP, puerto y PIN, luego prueba la conexion.", "Idioma", "Elige el idioma de la app. El ajuste se guarda en este telefono.", "Idioma de la app", "Idioma guardado.", "Ajustes de conexion", "Estos valores deben coincidir con el servidor del PC.", "IP del PC", "Ejemplo: 192.168.1.25", "Puerto", "Normalmente 8765", "Codigo de acceso del servidor", "Guardar ajustes", "Recordar IP, puerto y PIN", "Probar conexion", "Comprobar que el servidor del PC responde", "Controles del PC", "Los comandos se envian al PC en tu red local.", "Sonido", "Activar/desactivar silencio", "Bloquear", "Bloquear escritorio", "Suspender", "Poner el PC en suspension", "Reiniciar", "Reiniciar ahora", "Apagar", "Apagado completo", "Importante: la app funciona cuando el PC y el telefono estan en la misma red y el servidor del PC esta activo.", "Enviar este comando al PC?", "Cancelar", "Enviar", "Enviando solicitud...", "Ajustes guardados.", "La conexion funciona.", "Error: ", "enviado.", "PIN incorrecto o el servidor rechazo la solicitud", "Comando");
        if ("fr".equals(code)) return latin("Telecommande locale", "Controle ton PC depuis le telephone : son, verrouillage, veille, redemarrage et arret.", "Pret. Verifie l'IP, le port et le PIN, puis teste la connexion.", "Langue", "Choisis la langue de l'application. Le reglage est enregistre sur ce telephone.", "Langue de l'app", "Langue enregistree.", "Parametres de connexion", "Ces valeurs doivent correspondre au serveur sur le PC.", "Adresse IP du PC", "Exemple : 192.168.1.25", "Port", "Generalement 8765", "Code d'acces du serveur", "Enregistrer", "Memoriser IP, port et PIN", "Tester la connexion", "Verifier que le serveur PC repond", "Commandes du PC", "Les commandes sont envoyees au PC sur ton reseau local.", "Son", "Activer/desactiver muet", "Verrouiller", "Verrouiller le bureau", "Veille", "Mettre le PC en veille", "Redemarrer", "Redemarrer maintenant", "Eteindre", "Arret complet", "Important : l'app fonctionne quand le PC et le telephone sont sur le meme reseau et que le serveur PC tourne.", "Envoyer cette commande au PC ?", "Annuler", "Envoyer", "Envoi de la requete...", "Parametres enregistres.", "La connexion fonctionne.", "Erreur : ", "envoye.", "PIN incorrect ou serveur a refuse la requete", "Commande");
        return latin("Pilot lokalny", "Steruj PC z telefonu: dzwiek, blokada, uspienie, restart i wylaczenie.", "Gotowe. Sprawdz IP, port i PIN, potem przetestuj polaczenie.", "Jezyk", "Wybierz jezyk aplikacji. Ustawienie zapisze sie na tym telefonie.", "Jezyk aplikacji", "Jezyk zapisany.", "Ustawienia polaczenia", "Te wartosci musza pasowac do serwera na PC.", "Adres IP PC", "Przyklad: 192.168.1.25", "Port", "Zwykle 8765", "Kod dostepu do serwera", "Zapisz ustawienia", "Zapamietaj IP, port i PIN", "Test polaczenia", "Sprawdz, czy serwer PC odpowiada", "Sterowanie PC", "Komendy sa wysylane do PC w lokalnej sieci.", "Dzwiek", "Wl/wyl wyciszenie", "Blokada", "Zablokuj pulpit", "Uspij", "Uspij PC", "Restart", "Restartuj od razu", "Wylacz", "Pelne wylaczenie", "Wazne: aplikacja dziala, gdy PC i telefon sa w tej samej sieci, a serwer PC jest uruchomiony.", "Wyslac te komende do PC?", "Anuluj", "Wyslij", "Wysylam zadanie...", "Ustawienia zapisane.", "Polaczenie dziala.", "Blad: ", "wyslano.", "zly PIN albo serwer odrzucil zadanie", "Komenda");
    }

    private Map<String, String> latin(String eyebrow, String subtitle, String ready, String languageTitle, String languageSubtitle, String languageLabel, String languageSaved, String settingsTitle, String settingsSubtitle, String hostLabel, String hostHint, String portLabel, String portHint, String pinHint, String saveTitle, String saveSub, String testTitle, String testSub, String controlsTitle, String controlsSubtitle, String muteTitle, String muteSub, String lockTitle, String lockSub, String sleepTitle, String sleepSub, String restartTitle, String restartSub, String shutdownTitle, String shutdownSub, String note, String confirmMessage, String cancel, String send, String sending, String settingsSaved, String connectionOk, String errorPrefix, String sentSuffix, String loginFailed, String command) {
        return dict("eyebrow", eyebrow, "subtitle", subtitle, "ready", ready, "languageTitle", languageTitle, "languageSubtitle", languageSubtitle, "languageLabel", languageLabel, "languageSaved", languageSaved, "settingsTitle", settingsTitle, "settingsSubtitle", settingsSubtitle, "hostLabel", hostLabel, "hostHint", hostHint, "portLabel", portLabel, "portHint", portHint, "pinHint", pinHint, "saveTitle", saveTitle, "saveSub", saveSub, "testTitle", testTitle, "testSub", testSub, "controlsTitle", controlsTitle, "controlsSubtitle", controlsSubtitle, "muteTitle", muteTitle, "muteSub", muteSub, "lockTitle", lockTitle, "lockSub", lockSub, "sleepTitle", sleepTitle, "sleepSub", sleepSub, "restartTitle", restartTitle, "restartSub", restartSub, "shutdownTitle", shutdownTitle, "shutdownSub", shutdownSub, "note", note, "confirmMessage", confirmMessage, "cancel", cancel, "send", send, "sending", sending, "settingsSaved", settingsSaved, "connectionOk", connectionOk, "errorPrefix", errorPrefix, "sentSuffix", sentSuffix, "loginFailed", loginFailed, "command", command);
    }

    private Map<String, String> dict(String... pairs) {
        Map<String, String> map = new HashMap<>();
        for (int i = 0; i + 1 < pairs.length; i += 2) {
            map.put(pairs[i], pairs[i + 1]);
        }
        return map;
    }

    private static class DeviceProfile {
        final String name;
        final String host;
        final String port;
        final String pin;

        DeviceProfile(String name, String host, String port, String pin) {
            this.name = name == null || name.trim().isEmpty() ? "My PC" : name;
            this.host = host == null ? "" : host;
            this.port = port == null || port.trim().isEmpty() ? DEFAULT_PORT : port;
            this.pin = pin == null ? "" : pin;
        }
    }
}
