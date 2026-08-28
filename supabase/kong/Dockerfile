FROM kong/kong:3.9.1
USER root
COPY --chmod=755 kong-entrypoint.sh /home/kong/kong-entrypoint.sh
COPY --chown=kong:kong kong.yml /home/kong/temp.yml
USER kong
ENTRYPOINT ["bash", "/home/kong/kong-entrypoint.sh"]
