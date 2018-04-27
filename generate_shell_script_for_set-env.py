shfile = open('set-env.sh', 'w')
# change username and password
login_command = "cf login -a https://api.ng.bluemix.net\n"

shfile.write(login_command)

env = open('env')
app_name = env.readlines()[0].replace('APP_NAME = ','').replace('"','').strip()
env.close()

with open('env') as envfile:
    for line in envfile:
        shfile.write(f"cf set-env {app_name} {line.replace('= ', '')}")
