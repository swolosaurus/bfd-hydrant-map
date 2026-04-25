/*
 * Copyright 2020 Google Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package io.github.swolosaurus.bfdhydrants;

import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.widget.Toast;



public class LauncherActivity
        extends com.google.androidbrowserhelper.trusted.LauncherActivity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // Setting an orientation crashes the app due to the transparent background on Android 8.0
        // Oreo and below. We only set the orientation on Oreo and above. This only affects the
        // splash screen and Chrome will still respect the orientation.
        // See https://github.com/GoogleChromeLabs/bubblewrap/issues/496 for details.
        if (Build.VERSION.SDK_INT > Build.VERSION_CODES.O) {
            setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_USER_PORTRAIT);
        } else {
            setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED);
        }
    }

    @Override
    protected Uri getLaunchingUrl() {
        // Get the original launch Url.
        Uri uri = super.getLaunchingUrl();

        // Diagnostic: show the raw incoming URI in a Toast so we can see
        // exactly what NowForce is firing at us. Remove once auto-fill works.
        try {
            Intent intent = getIntent();
            String raw = (intent != null && intent.getData() != null)
                    ? intent.getData().toString()
                    : String.valueOf(uri);
            Toast.makeText(this, "Incoming: " + raw, Toast.LENGTH_LONG).show();
        } catch (Exception e) {
            // ignore
        }

        String address = extractAddress(uri);
        if (address != null && !address.isEmpty()) {
            return Uri.parse("https://swolosaurus.github.io/bfd-hydrant-map/")
                    .buildUpon()
                    .appendQueryParameter("address", address)
                    .build();
        }
        return uri;
    }

    /** Extract a usable address/query string from any maps-style URI. */
    private static String extractAddress(Uri uri) {
        if (uri == null) return null;
        String scheme = uri.getScheme();
        if (scheme == null) return null;

        // geo:LAT,LNG?q=ADDRESS  or geo:0,0?q=ADDRESS
        if ("geo".equals(scheme)) {
            String ssp = uri.getSchemeSpecificPart();
            if (ssp == null) return null;
            int qIdx = ssp.indexOf("?");
            String coords = qIdx >= 0 ? ssp.substring(0, qIdx) : ssp;
            String query = qIdx >= 0 ? ssp.substring(qIdx + 1) : "";
            if (!query.isEmpty()) {
                for (String param : query.split("&")) {
                    if (param.startsWith("q=")) {
                        return Uri.decode(param.substring(2));
                    }
                }
            }
            if (coords != null && !coords.equals("0,0")) return coords;
            return null;
        }

        // https://maps.google.com/?q=ADDRESS
        // https://www.google.com/maps/search/?api=1&query=ADDRESS
        // https://www.google.com/maps/place/ADDRESS
        // https://maps.apple.com/?q=ADDRESS
        if ("https".equals(scheme) || "http".equals(scheme)) {
            String q = uri.getQueryParameter("q");
            if (q != null && !q.isEmpty()) return q;
            String query = uri.getQueryParameter("query");
            if (query != null && !query.isEmpty()) return query;
            String daddr = uri.getQueryParameter("daddr");
            if (daddr != null && !daddr.isEmpty()) return daddr;
            String path = uri.getPath();
            if (path != null) {
                String[] markers = {"/maps/place/", "/maps/search/", "/maps/dir/"};
                for (String m : markers) {
                    int idx = path.indexOf(m);
                    if (idx >= 0) {
                        String tail = path.substring(idx + m.length());
                        int slash = tail.indexOf('/');
                        if (slash >= 0) tail = tail.substring(0, slash);
                        if (!tail.isEmpty()) return Uri.decode(tail);
                    }
                }
            }
        }
        return null;
    }
}
