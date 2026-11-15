FROM node:24-alpine@sha256:116b800c3754b440ee0aa3ed2f20f5bf3d99a554bfd9adeea09ea8017f6e85f5
ENV NODE_ENV=production HOST=0.0.0.0 PORT=4173
ARG SIGNAL_SOURCE_REVISION
LABEL org.opencontainers.image.revision=$SIGNAL_SOURCE_REVISION
WORKDIR /app
RUN mkdir /app/state && chown node:node /app/state
COPY --chown=node:node public ./public
COPY --chown=node:node fixtures ./fixtures
COPY --chown=node:node stress ./stress
COPY --chown=node:node server.mjs services.mjs benchmark.mjs evaluation-v2.mjs ./
USER node
EXPOSE 4173
HEALTHCHECK --interval=30s --timeout=3s CMD node -e "fetch('http://127.0.0.1:4173/api/ready').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node","server.mjs"]
