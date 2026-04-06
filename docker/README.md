# To stop the running container, purge the container and remove the image
1. docker ps
2. docker stop champion_path_job
3. docker container prune -f
4. docker images
5. docker image rm champion_path


# To build the docker image:
1. cd docker file directory
2. docker build -t champion_path .

# To run the container and make it restart automatically after reboot:
1. Create the fixture pdf files archive directory under /var/champion_path/archive on the host
1. Create the gz data files directory under /var/www/championpath/data on the host
2. docker run -d --restart=always --name champion_path_job -v /var/champion_path/archive:/app/archive -v /var/www/championpath/data:/app/local_data champion_path


# To logon to the container
1. docker exec -it champion_path_job /bin/bash