#!/bin/bash
docker login nexus-dock-priv.devops.msccruises.com -u 'ocp4' -p 'fd954a0472f2dd30'
docker buildx build --platform linux/amd64 -t msc/actionsync:v22 .
docker tag msc/actionsync:v22 nexus-dock-priv.devops.msccruises.com/otalio-virtualconcierge/actionsync:v22
docker push nexus-dock-priv.devops.msccruises.com/otalio-virtualconcierge/actionsync:v22
