SSR_PATH=/opt/sqlbot/g2-ssr
APP_PATH=/opt/sqlbot/app
nohup node $SSR_PATH/app.js &

cd $APP_PATH
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers
