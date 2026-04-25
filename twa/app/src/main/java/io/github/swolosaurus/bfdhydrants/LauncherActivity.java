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

import android.content.pm.ActivityInfo;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;



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

        // Intercept geo: URIs from other apps (e.g. NowForce "open in maps")
        // and rewrite them to the PWA URL with ?address= so the PWA auto-searches.
        if (uri != null && "geo".equals(uri.getScheme())) {
            String ssp = uri.getSchemeSpecificPart();
            String address = "";
            if (ssp != null) {
                int qIdx = ssp.indexOf("?");
                String coords = qIdx >= 0 ? ssp.substring(0, qIdx) : ssp;
                String query = qIdx >= 0 ? ssp.substring(qIdx + 1) : "";
                if (query != null && !query.isEmpty()) {
                    for (String param : query.split("&")) {
                        if (param.startsWith("q=")) {
                            address = Uri.decode(param.substring(2));
                            break;
                        }
                    }
                }
                if (address.isEmpty() && coords != null && !coords.equals("0,0")) {
                    address = coords;
                }
            }
            Uri.Builder builder = Uri.parse("https://swolosaurus.github.io/bfd-hydrant-map/").buildUpon();
            if (!address.isEmpty()) {
                builder.appendQueryParameter("address", address);
            }
            return builder.build();
        }

        return uri;
    }
}
