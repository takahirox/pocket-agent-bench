FROM mcr.microsoft.com/playwright:v1.56.1-noble@sha256:f1e7e01021efd65dd1a2c56064be399f3e4de00fd021ac561325f2bfbb2b837a
WORKDIR /verify
RUN npm init -y && npm install --ignore-scripts --no-audit --no-fund playwright@1.56.1
COPY browser-task.cjs ui-map.cjs /verify/
USER pwuser
ENTRYPOINT ["node", "/verify/browser-task.cjs"]
