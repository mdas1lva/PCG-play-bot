const HomePage = () => {

    const theme = ReactRedux.useSelector(state => state.theme);

    return (
        <div id={"outer-container"} data-theme={theme || "mocha"}>
            <div id={"center-container"}>

                <Header />
                <Body />
                <Footer />

            </div>
        </div>
    );
};


ReactDOM.render(
    <ReactRedux.Provider store={store}>
        <HomePage />
    </ReactRedux.Provider>,
    document.getElementById("root")
);
