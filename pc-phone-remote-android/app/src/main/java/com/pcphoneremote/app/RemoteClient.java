package com.pcphoneremote.app;

import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

/** A client is bound to one immutable device snapshot, including its session. */
final class RemoteClient {
    static final int FILE_LIMIT = 8 * 1024 * 1024;
    private final String base;
    private final String pin;
    private String cookie;

    RemoteClient(String host, String port, String pin) throws Exception {
        String address = host.trim();
        if (address.isEmpty()) throw new Exception("missingHost");
        if (!address.startsWith("http://") && !address.startsWith("https://")) {
            if (address.contains(":" ) && !address.startsWith("[")) address = "[" + address + "]";
            address = "http://" + address + ":" + (port.isEmpty() ? "8765" : port);
        }
        URL parsed = new URL(address);
        if (parsed.getHost().isEmpty() || parsed.getUserInfo() != null || parsed.getQuery() != null || parsed.getRef() != null)
            throw new Exception("invalidAddress");
        this.base = address.replaceAll("/+$", "");
        this.pin = pin;
    }

    JSONObject call(JSONObject payload) throws Exception {
        if (cookie == null) login();
        return request(payload, true);
    }

    private JSONObject request(JSONObject payload, boolean retryAuth) throws Exception {
        HttpURLConnection connection = connect("/api/v2");
        try {
            connection.setRequestProperty("Content-Type", "application/json");
            connection.setRequestProperty("Cookie", cookie);
            send(connection, payload.toString().getBytes(StandardCharsets.UTF_8));
            int code = connection.getResponseCode();
            if (code == 401 && retryAuth) {
                connection.disconnect();
                login();
                return request(payload, false);
            }
            if (code == 404) throw new Exception("updateServer");
            InputStream stream = code >= 400 ? connection.getErrorStream() : connection.getInputStream();
            String text = stream == null ? "" : new String(readLimited(stream, 12 * 1024 * 1024), StandardCharsets.UTF_8);
            JSONObject result;
            try { result = new JSONObject(text); }
            catch (Exception e) { throw new Exception("HTTP " + code); }
            if (code < 200 || code >= 300) throw new Exception(result.optString("message", "HTTP " + code));
            return result;
        } finally { connection.disconnect(); }
    }

    private void login() throws Exception {
        HttpURLConnection connection = connect("/login");
        try {
            connection.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
            send(connection, ("pin=" + URLEncoder.encode(pin, "UTF-8")).getBytes(StandardCharsets.UTF_8));
            int status = connection.getResponseCode();
            String header = connection.getHeaderField("Set-Cookie");
            if (status != 303 || header == null) throw new Exception(status == 429 ? "rateLimited" : "loginFailed");
            cookie = header.split(";", 2)[0];
        } finally { connection.disconnect(); }
    }

    private HttpURLConnection connect(String path) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(base + path).openConnection();
        connection.setInstanceFollowRedirects(false);
        connection.setConnectTimeout(6000);
        connection.setReadTimeout(30000);
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        return connection;
    }

    private void send(HttpURLConnection connection, byte[] bytes) throws Exception {
        connection.setFixedLengthStreamingMode(bytes.length);
        try (OutputStream output = connection.getOutputStream()) { output.write(bytes); }
    }

    static byte[] readLimited(InputStream input, int limit) throws Exception {
        if (input == null) throw new Exception("fileUnavailable");
        try (InputStream source = input; ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[16384];
            int count;
            while ((count = source.read(buffer)) != -1) {
                if (output.size() + count > limit) throw new Exception("fileLimit");
                output.write(buffer, 0, count);
            }
            return output.toByteArray();
        }
    }
}
