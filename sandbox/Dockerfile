FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        dbus-x11 \
        fonts-noto-cjk \
        fonts-noto-color-emoji \
        gnupg \
        imagemagick \
        libgbm1 \
        libnss3 \
        novnc \
        python3 \
        python3-pip \
        python3-venv \
        scrot \
        supervisor \
        vim \
        websockify \
        wget \
        x11-utils \
        x11vnc \
        xclip \
        xdotool \
        xdg-utils \
        xfce4 \
        xfce4-goodies \
        xfce4-terminal \
        xsel \
        xvfb \
    && install -d -m 0755 /etc/apt/keyrings \
    && wget -q https://packages.mozilla.org/apt/repo-signing-key.gpg -O /etc/apt/keyrings/packages.mozilla.org.asc \
    && echo "deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main" > /etc/apt/sources.list.d/mozilla.list \
    && printf 'Package: *\nPin: origin packages.mozilla.org\nPin-Priority: 1000\n' > /etc/apt/preferences.d/mozilla \
    && apt-get update \
    && apt-get install -y --no-install-recommends firefox \
    && rm -rf /var/lib/apt/lists/*

RUN install -d -m 0755 /usr/lib/firefox/distribution \
    && printf '%s\n' \
        '{' \
        '  "policies": {' \
        '    "DisableAppUpdate": true,' \
        '    "DisableFirefoxAccounts": true,' \
        '    "DisablePocket": true,' \
        '    "DontCheckDefaultBrowser": true,' \
        '    "OverrideFirstRunPage": "",' \
        '    "OverridePostUpdatePage": ""' \
        '  }' \
        '}' \
        > /usr/lib/firefox/distribution/policies.json

RUN groupadd --gid 1200 agent \
    && useradd --create-home --uid 1200 --gid 1200 --shell /bin/bash agent \
    && mkdir -p /home/agent/.config /home/agent/Downloads /workspace \
    && printf '{"name":"novnc","version":"1.3.0"}\n' > /usr/share/novnc/package.json \
    && chown -R agent:agent /home/agent /workspace

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY scripts/healthcheck.sh /usr/local/bin/healthcheck.sh
COPY scripts/screenshot.sh /usr/local/bin/screenshot.sh
COPY scripts/xdotool-smoke.sh /usr/local/bin/xdotool-smoke.sh
COPY scripts/paste_text.py /usr/local/bin/paste_text.py
COPY scripts/agent_action.py /usr/local/bin/agent_action.py

RUN chmod +x \
      /usr/local/bin/entrypoint.sh \
      /usr/local/bin/healthcheck.sh \
      /usr/local/bin/screenshot.sh \
      /usr/local/bin/xdotool-smoke.sh \
      /usr/local/bin/paste_text.py \
      /usr/local/bin/agent_action.py

EXPOSE 5900 6080

USER agent
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
