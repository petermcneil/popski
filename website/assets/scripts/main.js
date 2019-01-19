class CSSMode {
    constructor(mode, background, text, links, checked) {
        this.mode = mode;
        this.backgroundColour = background;
        this.textColour = text;
        this.linkColour = links;
        this.checked = checked;
    }
}

const modeToggle = document.getElementById("mode__toggle");

const themeColour = document.querySelector('meta[name="theme-color"]');
const msColour = document.querySelector('meta[name="msapplication-navbutton-color"]');
const appleColour = document.querySelector('meta[name="apple-mobile-web-app-status-bar-style"]');

const darkMode = new CSSMode("dark", "black", "white", "white", true);
const lightMode = new CSSMode("light", "white", "black", "blue", false);

function changeMode() {
    modeToggle.checked = document.documentElement
        .style
        .getPropertyValue('--background')
        .includes(darkMode.backgroundColour);

    toggleMode(modeToggle.checked);
}

function toggleMode(changeToLightMode) {
    let setCookie = true;
    if (typeof changeToLightMode === "string") {
        changeToLightMode = changeToLightMode === lightMode.mode || changeToLightMode === "";
        setCookie = false;
    }

    setMode(changeToLightMode ? lightMode : darkMode, setCookie);
}

function setMode(mode, setCookieB) {
    document.documentElement.style.setProperty('--text', mode.textColour);
    document.documentElement.style.setProperty('--links', mode.linkColour);

    document.documentElement.style.setProperty('--background', mode.backgroundColour);

    themeColour.setAttribute("content", mode.backgroundColour);
    msColour.setAttribute("content", mode.backgroundColour);
    appleColour.setAttribute("content", "default");

    if (setCookieB) {
        setCookie(mode.mode);
    }
    modeToggle.checked = mode.checked;
}

function setCookie(mode) {
    let domain = window.location.hostname;
    let date = new Date();
    date.setMonth(date.getMonth() + 12);
    document.cookie = "mode=" + mode + ";expires=" + date + "; path=/; secure;domain=." + domain;
}

function getCookie(c_name) {
    let c_start, c_end;

    if (document.cookie.length > 0) {
        c_start = document.cookie.indexOf(c_name + "=");
        if (c_start !== -1) {
            c_start = c_start + c_name.length + 1;
            c_end = document.cookie.indexOf(";", c_start);
            if (c_end === -1) c_end = document.cookie.length;
            return unescape(document.cookie.substring(c_start, c_end));
        }
    }
    return "";
}

toggleMode(getCookie("mode"));