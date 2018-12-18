const mode = getCookie("mode");
const b = document.getElementById("mode__toggle");

function toggle() {
    if(document.documentElement.style.getPropertyValue('--text').includes("black")){
        turn("dark");
    } else {
        turn("light");
    }
}

function turn(mode) {
    if (mode === "light"){
        document.documentElement.style.setProperty('--text', 'black');
        document.documentElement.style.setProperty('--background', 'white');
        document.documentElement.style.setProperty('--links', 'blue');
        setCookie("light");
        b.checked = false;
    } else {
        document.documentElement.style.setProperty('--text', 'white');
        document.documentElement.style.setProperty('--background', 'black');
        document.documentElement.style.setProperty('--links', 'white');
        setCookie("dark");
        b.checked = true;
    }
}

function setCookie(mode) {
    let domain = window.location.hostname;
    let date = new Date();
    date.setMonth(date.getMonth() + 12);
    document.cookie="mode="+ mode + ";expires="+ date + "; path=/; secure;domain=." + domain;
}

function getCookie(c_name) {
    let c_start, c_end;

    if (document.cookie.length > 0) {
        c_start = document.cookie.indexOf(c_name + "=");
        if (c_start !== -1) {
            c_start = c_start + c_name.length + 1;
            c_end = document.cookie.indexOf(";", c_start);
            if (c_end === -1) {
                c_end = document.cookie.length;
            }
            return unescape(document.cookie.substring(c_start, c_end));
        }
    }
    return "";
}

if (mode === "") {
    turn("light");
} else {
    turn(mode);
}