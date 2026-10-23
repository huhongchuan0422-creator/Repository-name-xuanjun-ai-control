# CANDIDATE ONLY. Additional isolated GET assets; not installed by this change.
location ~ ^/community-preview/community/ui-preview/(index\.html|route-gallery\.html|sources\.js|preview\.js|preview\.css|original\.css)?$ {
    rewrite ^/community-preview(/community/ui-preview/.*)$ $1 break;
    proxy_pass http://unix:/run/xuanjun-community-preview/preview.sock:;
    proxy_http_version 1.1;
    proxy_set_header Host uk.wenwenwenyiyiyi.work;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Xuanjun-Client-IP "";
    proxy_set_header X-Xuanjun-Client-IP $remote_addr;
    proxy_set_header X-Forwarded-For "";
    proxy_set_header Forwarded "";
}
